from __future__ import annotations

from uuid import UUID

from opentelemetry import trace
from opentelemetry.trace import Tracer

from .models import (
    BM25_WHOLE_DOCUMENT_PROFILE,
    CampaignDocument,
    DocumentType,
    RetrievalProfile,
    TextSearchHit,
)
from .ports import CampaignDocumentRepository, CampaignDocumentSearch


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
