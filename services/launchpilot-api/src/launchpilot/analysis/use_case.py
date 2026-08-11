from __future__ import annotations

from typing import Protocol

from launchpilot.campaigns.contracts.access import CampaignScope, CampaignScopeResolver

from .contracts.campaign_analysis import AnalyzeCampaign, CampaignAnalysisResult


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
