from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, field_validator

from launchpilot.bootstrap.http_scope import AuthorizedCampaignScope
from launchpilot.bootstrap.wiring import text_retrieval_service
from launchpilot.knowledge.contracts.retrieval import (
    CampaignDocument,
    CampaignDocumentCatalog,
    DocumentType,
)

router = APIRouter(prefix="/campaigns", tags=["campaign-documents"])
TextRetrievalDependency = Annotated[
    CampaignDocumentCatalog, Depends(text_retrieval_service)
]


class CampaignDocumentInput(BaseModel):
    document_type: DocumentType
    title: str
    content: str
    source_ref: str

    @field_validator("title", "content", "source_ref")
    @classmethod
    def strip_document_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("document fields must not be blank")
        return value


@router.post(
    "/{campaign_id}/documents",
    response_model=CampaignDocument,
    status_code=status.HTTP_201_CREATED,
)
def add_campaign_document(
    payload: CampaignDocumentInput,
    scope: AuthorizedCampaignScope,
    documents: TextRetrievalDependency,
) -> CampaignDocument:
    return documents.add(
        CampaignDocument(
            campaign_id=scope.campaign_id,
            workspace_id=scope.workspace_id,
            **payload.model_dump(),
        )
    )


@router.post("/{campaign_id}/documents/reindex")
def reindex_campaign_documents(
    scope: AuthorizedCampaignScope,
    documents: TextRetrievalDependency,
) -> dict[str, int]:
    count = documents.rebuild_projection(
        workspace_id=scope.workspace_id, campaign_id=scope.campaign_id
    )
    return {"indexed_documents": count}
