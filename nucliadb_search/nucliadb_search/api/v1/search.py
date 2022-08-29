# Copyright (C) 2021 Bosutech XXI S.L.
#
# nucliadb is offered under the AGPL v3.0 and as commercial software.
# For commercial licensing, contact us at info@nuclia.com.
#
# AGPL:
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
import asyncio
from datetime import datetime
from time import time
from typing import List, Optional

from fastapi import Header, HTTPException, Query, Request, Response
from fastapi_versioning import version
from grpc import StatusCode as GrpcStatusCode
from grpc.aio import AioRpcError  # type: ignore
from nucliadb_protos.nodereader_pb2 import SearchResponse
from nucliadb_protos.writer_pb2 import ShardObject as PBShardObject
from sentry_sdk import capture_exception

from nucliadb_models.common import FieldTypeName
from nucliadb_models.resource import NucliaDBRoles
from nucliadb_models.serialize import ExtractedDataTypeName, ResourceProperties
from nucliadb_search import logger
from nucliadb_search.api.models import (
    KnowledgeboxSearchResults,
    SearchClientType,
    SearchOptions,
    SortOption,
)
from nucliadb_search.api.v1.router import KB_PREFIX, api
from nucliadb_search.search.fetch import abort_transaction  # type: ignore
from nucliadb_search.search.merge import merge_results
from nucliadb_search.search.query import global_query_to_pb
from nucliadb_search.search.shards import query_shard
from nucliadb_search.settings import settings
from nucliadb_search.utilities import get_counter, get_nodes
from nucliadb_utils.authentication import requires
from nucliadb_utils.exceptions import ShardsNotFound
from nucliadb_utils.utilities import get_audit


@api.get(
    f"/{KB_PREFIX}/{{kbid}}/search",
    status_code=200,
    description="Search on a knowledge box",
    response_model=KnowledgeboxSearchResults,
    response_model_exclude_unset=True,
    tags=["Search"],
)
@requires(NucliaDBRoles.READER)
@version(1)
async def search_knowledgebox(
    request: Request,
    response: Response,
    kbid: str,
    query: str = Query(default=..., min_length=3),
    fields: List[str] = Query(default=[]),
    filters: List[str] = Query(default=[]),
    faceted: List[str] = Query(default=[]),
    sort: SortOption = SortOption.CREATED,
    page_number: int = Query(default=0),
    page_size: int = Query(default=20),
    max_score: float = Query(default=0.73),
    range_creation_start: Optional[datetime] = Query(default=None),
    range_creation_end: Optional[datetime] = Query(default=None),
    range_modification_start: Optional[datetime] = Query(default=None),
    range_modification_end: Optional[datetime] = Query(default=None),
    features: List[SearchOptions] = Query(
        default=[
            SearchOptions.PARAGRAPH,
            SearchOptions.DOCUMENT,
            SearchOptions.VECTOR,
            SearchOptions.RELATIONS,
        ]
    ),
    reload: bool = Query(default=True),
    debug: bool = Query(default=False),
    highlight: bool = Query(default=False),
    split: bool = Query(default=False),
    show: List[ResourceProperties] = Query([ResourceProperties.BASIC]),
    field_type_filter: List[FieldTypeName] = Query(
        list(FieldTypeName), alias="field_type"
    ),
    extracted: List[ExtractedDataTypeName] = Query(list(ExtractedDataTypeName)),
    x_ndb_client: SearchClientType = Header(SearchClientType.API),
    x_nucliadb_user: str = Header(""),
    x_forwarded_for: str = Header(""),
) -> KnowledgeboxSearchResults:
    # We need the nodes/shards that are connected to the KB
    nodemanager = get_nodes()
    audit = get_audit()
    timeit = time()

    if query == "":
        # If query is not defined we force to not return results
        page_size = 1
        page_number = 0
        if SearchOptions.VECTOR in features:
            features.remove(SearchOptions.VECTOR)

    try:
        shard_groups: List[PBShardObject] = await nodemanager.get_shards_by_kbid(kbid)
    except ShardsNotFound:
        raise HTTPException(
            status_code=404,
            detail="The knowledgebox or its shards configuration is missing",
        )

    # We need to query all nodes
    pb_query = await global_query_to_pb(
        kbid,
        features,
        query,
        filters,
        faceted,
        sort.value,
        page_number,
        page_size,
        range_creation_start,
        range_creation_end,
        range_modification_start,
        range_modification_end,
        fields,
        reload,
    )

    incomplete_results = False
    ops = []
    queried_shards = []
    for shard in shard_groups:
        try:
            node, shard_id, node_id = nodemanager.choose_node(shard)
        except KeyError:
            incomplete_results = True
        else:
            if shard_id is not None:
                # At least one node is alive for this shard group
                # let's add it ot the query list if has a valid value
                ops.append(query_shard(node, shard_id, pb_query))
                queried_shards.append((node.label, shard_id, node_id))

    if not ops:
        await abort_transaction()
        logger.info(f"No node found for any of this resources shards {kbid}")
        raise HTTPException(
            status_code=500,
            detail=f"No node found for any of this resources shards {kbid}",
        )

    try:
        results: Optional[List[SearchResponse]] = await asyncio.wait_for(  # type: ignore
            asyncio.gather(*ops, return_exceptions=True),  # type: ignore
            timeout=settings.search_timeout,
        )
    except asyncio.TimeoutError as exc:
        capture_exception(exc)
        await abort_transaction()
        raise HTTPException(status_code=503, detail=f"Data query took too long")
    except AioRpcError as exc:
        if exc.code() is GrpcStatusCode.UNAVAILABLE:
            raise HTTPException(status_code=503, detail=f"Search backend not available")
        else:
            raise exc

    if results is None:
        await abort_transaction()
        raise HTTPException(
            status_code=500, detail=f"Error while executing shard queries"
        )

    for result in results:
        if isinstance(result, Exception):
            capture_exception(result)
            await abort_transaction()
            raise HTTPException(
                status_code=500, detail=f"Error while querying shard data"
            )

    # We need to merge
    search_results = await merge_results(
        results,
        count=page_size,
        page=page_number,
        kbid=kbid,
        show=show,
        field_type_filter=field_type_filter,
        extracted=extracted,
        max_score=max_score,
        highlight=highlight,
        split=split,
    )
    await abort_transaction()

    get_counter()[f"{kbid}_-_search_client_{x_ndb_client.value}"] += 1
    response.status_code = 206 if incomplete_results else 200
    if audit is not None:
        await audit.search(
            kbid,
            x_nucliadb_user,
            x_forwarded_for,
            pb_query,
            timeit - time(),
            len(search_results.resources),
        )
    if debug:
        search_results.shards = queried_shards
    return search_results
