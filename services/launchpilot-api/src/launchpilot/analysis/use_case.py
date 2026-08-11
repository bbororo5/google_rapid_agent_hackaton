from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from launchpilot.campaigns.public import CampaignScope, CampaignScopeResolver


@dataclass(frozen=True, slots=True)
class AnalyzeCampaign:
    user_id: UUID
    campaign_id: UUID
    question: str


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


class CampaignAnswerer(Protocol):
    def answer(self, question: str) -> CampaignAnalysisResult: ...


class CampaignAnswererFactory(Protocol):
    def create(self, scope: CampaignScope) -> CampaignAnswerer: ...


class CampaignAnalysisService:
    """Application controller for the complete campaign-analysis use case."""

    def __init__(
        self,
        access: CampaignScopeResolver,
        agents: CampaignAnswererFactory,
    ) -> None:
        self._access = access
        self._agents = agents

    def handle(self, command: AnalyzeCampaign) -> CampaignAnalysisResult:
        scope = self._access.authorize(
            user_id=command.user_id, campaign_id=command.campaign_id
        )
        return self._agents.create(scope).answer(command.question)
