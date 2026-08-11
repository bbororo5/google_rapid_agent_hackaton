from __future__ import annotations

from typing import Protocol
from uuid import UUID

from launchpilot.knowledge.public import CampaignDocument, DocumentType, TextSearchHit
from launchpilot.performance.public import CampaignMetricQuery, CampaignPerformance


class CampaignPerformanceReader(Protocol):
    """Message boundary used by analysis for exact metric retrieval."""

    def get_campaign_performance(
        self, query: CampaignMetricQuery
    ) -> CampaignPerformance | None: ...


class CampaignDocumentReader(Protocol):
    """Message boundary used by analysis for evidence document retrieval."""

    def search(
        self,
        *,
        workspace_id: UUID,
        campaign_id: UUID,
        query: str,
        document_types: tuple[DocumentType, ...] = (),
        top_k: int = 5,
    ) -> tuple[TextSearchHit, ...]: ...

    def resolve(
        self, *, document_id: UUID, workspace_id: UUID, campaign_id: UUID
    ) -> CampaignDocument | None: ...
