from datetime import UTC, date, datetime
from uuid import uuid4

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableLambda

from launchpilot.analysis.agent import CampaignAgent
from launchpilot.analysis.evidence import EvidenceCollector
from launchpilot.analysis.graph import AnalysisGraph
from launchpilot.analysis.tools import CampaignToolset
from launchpilot.campaigns.public import CampaignScope
from launchpilot.knowledge import (
    CampaignDocument,
    DocumentType,
    TextRetrievalService,
    TextSearchHit,
)
from launchpilot.performance.retrieval import (
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
    toolset = CampaignToolset(
        retrieval=StructuredRetrievalService(repository),
        text_retrieval=TextRetrievalService(None, None),  # type: ignore[arg-type]
        scope=CampaignScope(
            user_id=uuid4(),
            campaign_id=campaign_id,
            workspace_id=workspace_id,
        ),
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

    result = CampaignAgent(
        graph=AnalysisGraph(
            model_with_tools=RunnableLambda(scripted_model), tools=toolset.tools()
        ),
        evidence_collector=EvidenceCollector(),
    ).answer("7월 Google Ads 지출을 알려줘")

    assert "120,000 KRW" in result.answer
    assert len(result.evidence) == 1
    assert result.evidence[0].observation_id == observation_id
    assert result.evidence[0].kind == "METRIC"
    assert result.evidence[0].source_ref == "google-ads:fetch-1"
    assert repository.queries[0].campaign_id == campaign_id
    assert repository.queries[0].workspace_id == workspace_id
    assert repository.queries[0].start_date == date(2026, 7, 1)


def test_agent_searches_then_resolves_document_evidence() -> None:
    campaign_id = uuid4()
    workspace_id = uuid4()
    document = CampaignDocument(
        campaign_id=campaign_id,
        workspace_id=workspace_id,
        document_type=DocumentType.MEMO,
        title="소재 피로 메모",
        content="7월 17일부터 CTR이 하락했다.",
        source_ref="memo:fatigue",
    )

    class StubTextRetrieval:
        def search(self, **kwargs):
            assert kwargs["workspace_id"] == workspace_id
            return (
                TextSearchHit(
                    document_id=document.id,
                    campaign_id=campaign_id,
                    document_type=document.document_type,
                    title=document.title,
                    excerpt=document.content,
                    source_ref=document.source_ref,
                    score=2.0,
                    rank=1,
                    retrieval_method="bm25",
                    index_version="campaign-documents-v1",
                    chunker_version="whole-document-v1",
                    retriever_version="bm25-v1",
                ),
            )

        def resolve(self, **kwargs):
            assert kwargs["workspace_id"] == workspace_id
            return document

    toolset = CampaignToolset(
        retrieval=StructuredRetrievalService(StubRetrievalRepository(None)),  # type: ignore[arg-type]
        text_retrieval=StubTextRetrieval(),  # type: ignore[arg-type]
        scope=CampaignScope(
            user_id=uuid4(),
            campaign_id=campaign_id,
            workspace_id=workspace_id,
        ),
    )

    def scripted_model(messages):
        tool_messages = [
            message for message in messages if isinstance(message, ToolMessage)
        ]
        if not tool_messages:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "search_campaign_documents",
                        "args": {"query": "소재 피로 CTR"},
                        "id": "search-1",
                        "type": "tool_call",
                    }
                ],
            )
        if len(tool_messages) == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "resolve_campaign_document",
                        "args": {"document_id": str(document.id)},
                        "id": "resolve-1",
                        "type": "tool_call",
                    }
                ],
            )
        return AIMessage(content="소재 피로 메모에 CTR 하락이 기록되어 있습니다.")

    result = CampaignAgent(
        graph=AnalysisGraph(
            model_with_tools=RunnableLambda(scripted_model), tools=toolset.tools()
        ),
        evidence_collector=EvidenceCollector(),
    ).answer("CTR 하락과 관련된 메모를 찾아줘")

    assert result.evidence[0].kind == "DOCUMENT"
    assert result.evidence[0].document_id == document.id
    assert result.evidence[0].source_ref == "memo:fatigue"
