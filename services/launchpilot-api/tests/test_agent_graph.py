from datetime import UTC, date, datetime
from uuid import uuid4

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableLambda

from launchpilot.agent.campaign_analysis import (
    CampaignAnalysisAgent,
    campaign_retrieval_tools,
)
from launchpilot.application.retrieval import (
    CampaignPerformance,
    CampaignSummary,
    MetricEvidence,
    StructuredRetrievalService,
)


class StubRetrievalRepository:
    def __init__(self, result: CampaignPerformance) -> None:
        self.result = result
        self.queries = []

    def get_campaign_performance(self, query):
        self.queries.append(query)
        return self.result


def test_agent_calls_scoped_retrieval_and_returns_evidence() -> None:
    campaign_id = uuid4()
    workspace_id = uuid4()
    observation_id = uuid4()
    repository = StubRetrievalRepository(
        CampaignPerformance(
            campaign=CampaignSummary(
                id=campaign_id,
                name="Summer Campaign",
                goal="Acquire customers",
                period_start=date(2026, 7, 1),
                period_end=date(2026, 7, 31),
                target_metrics=("spend",),
            ),
            metrics=(
                MetricEvidence(
                    observation_id=observation_id,
                    captured_at=datetime(2026, 8, 1, tzinfo=UTC),
                    completeness_status="COMPLETE",
                    missing_reasons=(),
                    surface="GOOGLE_ADS",
                    connector="google-ads-rest-v25",
                    account_ref="customers/1",
                    external_campaign_ref="1",
                    subject_ref="google-ads-campaign:1",
                    subject_level="CAMPAIGN",
                    metric_key="spend",
                    value=120000,
                    unit="currency:KRW",
                    period_start=date(2026, 7, 1),
                    period_end=date(2026, 7, 31),
                    provenance_ref="google-ads:fetch-1",
                    calculation=None,
                ),
            ),
        )
    )
    tools = campaign_retrieval_tools(
        retrieval=StructuredRetrievalService(repository),
        campaign_id=campaign_id,
        workspace_id=workspace_id,
    )

    def scripted_model(messages):
        if any(isinstance(message, ToolMessage) for message in messages):
            return AIMessage(
                content=(
                    "지출은 120,000 KRW입니다. "
                    "[GOOGLE_ADS | google-ads:fetch-1 | 2026-08-01]"
                )
            )
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "get_campaign_performance",
                    "args": {
                        "start_date": "2026-07-01",
                        "end_date": "2026-07-31",
                        "platforms": ["GOOGLE_ADS"],
                        "metric_keys": ["spend"],
                    },
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
        )

    result = CampaignAnalysisAgent(
        model_with_tools=RunnableLambda(scripted_model), tools=tools
    ).analyze("7월 Google Ads 지출을 알려줘")

    assert "120,000 KRW" in result.answer
    assert len(result.evidence) == 1
    assert result.evidence[0].observation_id == observation_id
    assert repository.queries[0].campaign_id == campaign_id
    assert repository.queries[0].workspace_id == workspace_id
    assert repository.queries[0].start_date == date(2026, 7, 1)
