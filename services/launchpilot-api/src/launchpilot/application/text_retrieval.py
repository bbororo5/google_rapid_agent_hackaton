from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4

from opentelemetry import trace
from opentelemetry.trace import Tracer
from pydantic import BaseModel, ConfigDict, Field


class DocumentType(StrEnum):
    MEMO = "MEMO"
    BRIEF = "BRIEF"
    ANALYSIS = "ANALYSIS"


class RetrievalMethod(StrEnum):
    BM25 = "bm25"


class RetrievalProfile(BaseModel):
    """Identifies the retrieval configuration that produced a result."""

    model_config = ConfigDict(frozen=True)

    method: RetrievalMethod
    index_version: str = Field(min_length=1)
    chunker_version: str = Field(min_length=1)
    retriever_version: str = Field(min_length=1)


BM25_WHOLE_DOCUMENT_PROFILE = RetrievalProfile(
    method=RetrievalMethod.BM25,
    index_version="campaign-documents-v1",
    chunker_version="whole-document-v1",
    retriever_version="bm25-v1",
)


class CampaignDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    campaign_id: UUID
    workspace_id: UUID
    document_type: DocumentType
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TextSearchHit(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: UUID
    campaign_id: UUID
    chunk_id: str | None = None
    document_type: DocumentType
    title: str
    excerpt: str
    source_ref: str
    score: float
    rank: int = Field(ge=1)
    retrieval_method: RetrievalMethod
    index_version: str
    chunker_version: str
    retriever_version: str


class CampaignDocumentRepository(Protocol):
    def add(self, document: CampaignDocument) -> None: ...
    def list_scoped(
        self, *, workspace_id: UUID, campaign_id: UUID
    ) -> tuple[CampaignDocument, ...]: ...
    def get_scoped(
        self, *, document_id: UUID, workspace_id: UUID, campaign_id: UUID
    ) -> CampaignDocument | None: ...


class CampaignDocumentSearch(Protocol):
    @property
    def profile(self) -> RetrievalProfile: ...

    def index(self, document: CampaignDocument) -> None: ...
    def search(
        self,
        *,
        workspace_id: UUID,
        campaign_id: UUID,
        query: str,
        document_types: tuple[DocumentType, ...] = (),
        top_k: int = 5,
    ) -> tuple[TextSearchHit, ...]: ...


class TextRetrievalService:
    def __init__(
        self,
        repository: CampaignDocumentRepository,
        search: CampaignDocumentSearch,
        *,
        profile: RetrievalProfile = BM25_WHOLE_DOCUMENT_PROFILE,
        tracer: Tracer | None = None,
    ) -> None:
        self._repository = repository
        self._search = search
        self._profile = getattr(search, "profile", profile)
        self._tracer = tracer or trace.get_tracer(__name__)

    def add(self, document: CampaignDocument) -> CampaignDocument:
        self._repository.add(document)
        self._search.index(document)
        return document

    def search(
        self,
        *,
        workspace_id: UUID,
        campaign_id: UUID,
        query: str,
        document_types: tuple[DocumentType, ...] = (),
        top_k: int = 5,
    ) -> tuple[TextSearchHit, ...]:
        with self._tracer.start_as_current_span(
            "launchpilot.retrieval.text.search"
        ) as span:
            span.set_attribute("launchpilot.retrieval.method", self._profile.method)
            span.set_attribute(
                "launchpilot.retrieval.index_version", self._profile.index_version
            )
            span.set_attribute(
                "launchpilot.retrieval.chunker_version", self._profile.chunker_version
            )
            span.set_attribute(
                "launchpilot.retrieval.retriever_version",
                self._profile.retriever_version,
            )
            span.set_attribute("launchpilot.retrieval.top_k", top_k)
            span.set_attribute("launchpilot.retrieval.query_length", len(query))
            span.set_attribute(
                "launchpilot.retrieval.document_type_filter_count",
                len(document_types),
            )
            hits = self._search.search(
                workspace_id=workspace_id,
                campaign_id=campaign_id,
                query=query,
                document_types=document_types,
                top_k=top_k,
            )
            span.set_attribute("launchpilot.retrieval.returned_count", len(hits))
            return hits

    def resolve(
        self, *, document_id: UUID, workspace_id: UUID, campaign_id: UUID
    ) -> CampaignDocument | None:
        return self._repository.get_scoped(
            document_id=document_id,
            workspace_id=workspace_id,
            campaign_id=campaign_id,
        )

    def rebuild_projection(self, *, workspace_id: UUID, campaign_id: UUID) -> int:
        documents = self._repository.list_scoped(
            workspace_id=workspace_id, campaign_id=campaign_id
        )
        for document in documents:
            self._search.index(document)
        return len(documents)
