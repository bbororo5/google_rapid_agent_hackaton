from datetime import date
from uuid import uuid4

import pytest

from launchpilot.analysis.use_case import (
    AnalyzeCampaign,
    CampaignAccessService,
    CampaignAnalysisResult,
    CampaignAnalysisService,
)
from launchpilot.campaigns.models import Campaign
from launchpilot.campaigns.service import CampaignService
from launchpilot.shared import DateRange
from launchpilot.shared.errors import NotFoundError


class CampaignRepositoryStub:
    def __init__(self, campaign: Campaign) -> None:
        self.campaign = campaign

    def get(self, campaign_id):
        return self.campaign if campaign_id == self.campaign.id else None

    def add(self, campaign):
        self.campaign = campaign

    def list(self):
        return [self.campaign]

    def list_by_workspaces(self, workspace_ids):
        return [self.campaign] if self.campaign.workspace_id in workspace_ids else []


class WorkspaceAccessStub:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed

    def allows(self, *, user_id, workspace_id):
        return self.allowed


class AnswererStub:
    def __init__(self) -> None:
        self.questions: list[str] = []

    def answer(self, question: str) -> CampaignAnalysisResult:
        self.questions.append(question)
        return CampaignAnalysisResult(answer="grounded answer", evidence=())


class AgentFactoryStub:
    def __init__(self, answerer: AnswererStub) -> None:
        self.answerer = answerer
        self.scopes = []

    def create(self, scope):
        self.scopes.append(scope)
        return self.answerer


def test_analysis_service_authorizes_scope_then_sends_question_to_agent() -> None:
    campaign = _campaign()
    user_id = uuid4()
    answerer = AnswererStub()
    agents = AgentFactoryStub(answerer)
    service = CampaignAnalysisService(
        access=CampaignAccessService(
            CampaignService(CampaignRepositoryStub(campaign)),
            WorkspaceAccessStub(True),
        ),
        agents=agents,
    )

    result = service.handle(
        AnalyzeCampaign(
            user_id=user_id,
            campaign_id=campaign.id,
            question="성과를 분석해줘",
        )
    )

    assert result.answer == "grounded answer"
    assert agents.scopes[0].user_id == user_id
    assert agents.scopes[0].workspace_id == campaign.workspace_id
    assert answerer.questions == ["성과를 분석해줘"]


def test_analysis_service_does_not_create_agent_when_access_is_denied() -> None:
    campaign = _campaign()
    agents = AgentFactoryStub(AnswererStub())
    service = CampaignAnalysisService(
        access=CampaignAccessService(
            CampaignService(CampaignRepositoryStub(campaign)),
            WorkspaceAccessStub(False),
        ),
        agents=agents,
    )

    with pytest.raises(NotFoundError, match="campaign not found"):
        service.handle(
            AnalyzeCampaign(
                user_id=uuid4(), campaign_id=campaign.id, question="분석해줘"
            )
        )

    assert agents.scopes == []


def _campaign() -> Campaign:
    return Campaign.create(
        workspace_id=uuid4(),
        name="Analysis Campaign",
        goal="Test object collaboration",
        period=DateRange(date(2026, 7, 1), date(2026, 7, 31)),
    )
