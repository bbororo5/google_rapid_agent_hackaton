from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from .search_profile import RetrievalMethod


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
