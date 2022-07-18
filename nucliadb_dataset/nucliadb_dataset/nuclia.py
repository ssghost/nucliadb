from typing import Iterator
import grpc
from nucliadb_protos.train_pb2_grpc import TrainStub
from nucliadb_protos.train_pb2 import (
    GetSentencesRequest,
    GetParagraphsRequest,
    GetResourcesRequest,
    GetFieldsRequest,
    TrainSentence,
    TrainParagraph,
    TrainResource,
    TrainField,
)


class NucliaDriver:
    def __init__(self, grpc_address: str):
        self.grpc_address = grpc_address

        self.channel = grpc.insecure_channel(grpc_address)
        self.stub = TrainStub(self.channel)

    def iterate_sentences(
        self, kbid: str, labels: bool, entities: bool, text: bool
    ) -> Iterator[TrainSentence]:
        request = GetSentencesRequest()
        request.kb.uuid = kbid
        request.metadata.labels = labels
        request.metadata.entities = entities
        request.metadata.text = text
        for sentence in self.stub.GetSentences(request):
            yield sentence

    def iterate_paragraphs(
        self, kbid: str, labels: bool, entities: bool, text: bool
    ) -> Iterator[TrainParagraph]:
        request = GetParagraphsRequest()
        request.kb.uuid = kbid
        request.metadata.labels = labels
        request.metadata.entities = entities
        request.metadata.text = text
        for paragraph in self.stub.GetParagraphs(request):
            yield paragraph

    def iterate_resources(
        self, kbid: str, labels: bool, entities: bool, text: bool
    ) -> Iterator[TrainResource]:
        request = GetResourcesRequest()
        request.kb.uuid = kbid
        request.metadata.labels = labels
        request.metadata.entities = entities
        request.metadata.text = text
        for resource in self.stub.GetResources(request):
            yield resource

    def iterate_fields(
        self, kbid: str, labels: bool, entities: bool, text: bool
    ) -> Iterator[TrainField]:
        request = GetFieldsRequest()
        request.kb.uuid = kbid
        request.metadata.labels = labels
        request.metadata.entities = entities
        request.metadata.text = text
        for field in self.stub.GetFields(request):
            yield field

    def get_labels(self, kbid: str) -> TrainField:
        request = GetFieldsRequest()
        request.kb.uuid = kbid
        request.metadata.labels = labels
        request.metadata.entities = entities
        request.metadata.text = text
        for field in self.stub.GetFields(request):
            yield field