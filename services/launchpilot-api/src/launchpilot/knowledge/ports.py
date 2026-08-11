from collections.abc import Iterator
from contextlib import contextmanager
from typing import Protocol
from uuid import UUID

from .contracts.observability import RetrievalSearchObservation
from .contracts.retrieval import (
    CampaignDocument,
    DocumentType,
    TextSearchHit,
)
from .contracts.search_profile import RetrievalProfile


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


class _NullRetrievalSearchObservation:
    def returned(self, count: int) -> None:
        pass


class NullRetrievalObserver:
    @contextmanager
    def observe_search(
        self,
        *,
        profile: RetrievalProfile,
        query_length: int,
        document_type_filter_count: int,
        top_k: int,
    ) -> Iterator[RetrievalSearchObservation]:
        yield _NullRetrievalSearchObservation()
