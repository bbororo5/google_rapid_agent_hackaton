from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class DocumentType(StrEnum):
    MEMO = "MEMO"
    BRIEF = "BRIEF"
    ANALYSIS = "ANALYSIS"


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
    document_type: DocumentType
    title: str
    excerpt: str
    source_ref: str
    score: float


class CampaignDocumentRepository(Protocol):
    def add(self, document: CampaignDocument) -> None: ...
    def list_scoped(
        self, *, workspace_id: UUID, campaign_id: UUID
    ) -> tuple[CampaignDocument, ...]: ...
    def get_scoped(
        self, *, document_id: UUID, workspace_id: UUID, campaign_id: UUID
    ) -> CampaignDocument | None: ...


class CampaignDocumentSearch(Protocol):
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
    ) -> None:
        self._repository = repository
        self._search = search

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
        return self._search.search(
            workspace_id=workspace_id,
            campaign_id=campaign_id,
            query=query,
            document_types=document_types,
            top_k=top_k,
        )

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
