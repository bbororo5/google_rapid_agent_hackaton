from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from launchpilot.campaigns.service import CampaignService
from launchpilot.shared.errors import NotFoundError


@dataclass(frozen=True, slots=True)
class AnalyzeCampaign:
    user_id: UUID
    campaign_id: UUID
    question: str


@dataclass(frozen=True, slots=True)
class AnalysisScope:
    user_id: UUID
    workspace_id: UUID
    campaign_id: UUID


class AgentEvidenceRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["METRIC", "DOCUMENT"]
    source_ref: str
    captured_at: str
    observation_id: UUID | None = None
    document_id: UUID | None = None
    surface: str | None = None
    metric_key: str | None = None


class CampaignAnalysisResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    answer: str
    evidence: tuple[AgentEvidenceRef, ...]


class WorkspaceAccessReader(Protocol):
    def allows(self, *, user_id: UUID, workspace_id: UUID) -> bool: ...


class CampaignAnswerer(Protocol):
    def answer(self, question: str) -> CampaignAnalysisResult: ...


class CampaignAnswererFactory(Protocol):
    def create(self, scope: AnalysisScope) -> CampaignAnswerer: ...


class CampaignAccessService:
    def __init__(
        self, campaigns: CampaignService, workspace_access: WorkspaceAccessReader
    ) -> None:
        self._campaigns = campaigns
        self._workspace_access = workspace_access

    def authorize(self, *, user_id: UUID, campaign_id: UUID) -> AnalysisScope:
        campaign = self._campaigns.get(campaign_id)
        if not self._workspace_access.allows(
            user_id=user_id, workspace_id=campaign.workspace_id
        ):
            raise NotFoundError("campaign not found")
        return AnalysisScope(
            user_id=user_id,
            workspace_id=campaign.workspace_id,
            campaign_id=campaign.id,
        )


class CampaignAnalysisService:
    """Application controller for the complete campaign-analysis use case."""

    def __init__(
        self,
        access: CampaignAccessService,
        agents: CampaignAnswererFactory,
    ) -> None:
        self._access = access
        self._agents = agents

    def handle(self, command: AnalyzeCampaign) -> CampaignAnalysisResult:
        scope = self._access.authorize(
            user_id=command.user_id, campaign_id=command.campaign_id
        )
        return self._agents.create(scope).answer(command.question)
