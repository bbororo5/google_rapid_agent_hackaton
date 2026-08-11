from __future__ import annotations

from uuid import UUID

from .contracts.observability import RetrievalObserver
from .contracts.retrieval import (
    CampaignDocument,
    DocumentType,
    TextSearchHit,
)
from .contracts.search_profile import (
    BM25_WHOLE_DOCUMENT_PROFILE,
    RetrievalProfile,
)
from .ports import (
    CampaignDocumentRepository,
    CampaignDocumentSearch,
    NullRetrievalObserver,
)


class TextRetrievalService:
    def __init__(
        self,
        repository: CampaignDocumentRepository,
        search: CampaignDocumentSearch,
        *,
        profile: RetrievalProfile = BM25_WHOLE_DOCUMENT_PROFILE,
        observer: RetrievalObserver | None = None,
    ) -> None:
        self._repository = repository
        self._search = search
        self._profile = getattr(search, "profile", profile)
        self._observer = observer or NullRetrievalObserver()

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
        with self._observer.observe_search(
            profile=self._profile,
            query_length=len(query),
            document_type_filter_count=len(document_types),
            top_k=top_k,
        ) as observation:
            hits = self._search.search(
                workspace_id=workspace_id,
                campaign_id=campaign_id,
                query=query,
                document_types=document_types,
                top_k=top_k,
            )
            observation.returned(len(hits))
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
