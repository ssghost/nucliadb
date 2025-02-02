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
from nucliadb.ingest.fields.base import Field

VALID_GLOBAL = ("title", "summary")


class Generic(Field):
    pbklass = str
    value: str
    type: str = "a"

    async def set_value(self, payload: str):
        if self.id not in VALID_GLOBAL:
            raise AttributeError(self.id)

        if self.resource.basic is None:
            await self.resource.get_basic()

        setattr(self.resource.basic, self.id, payload)

    async def get_value(self) -> str:
        if self.id not in VALID_GLOBAL:
            raise AttributeError(self.id)
        if self.resource.basic is None:
            await self.resource.get_basic()

        return getattr(self.resource.basic, self.id)
