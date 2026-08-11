from typing import Protocol
from uuid import UUID

from .models import (
    CampaignDocument,
    DocumentType,
    RetrievalProfile,
    TextSearchHit,
)


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
