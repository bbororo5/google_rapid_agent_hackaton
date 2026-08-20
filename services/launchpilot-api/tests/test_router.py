from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import StructuredTool

from launchpilot.analysis.graph import AnalysisGraph
from launchpilot.analysis.prompts import format_system_prompt
from launchpilot.analysis.router import QueryRoute, QueryRouter, ScopeRouter
from launchpilot.analysis.scope import ExecutionScope


def test_query_router_classifies_core_profiles() -> None:
    router = QueryRouter()

    assert router.classify("C0010 캠페인의 지난주 ROAS를 알려줘") == QueryRoute.STRUCTURED_METRIC
    assert router.classify("C0010 캠페인의 소재 피로 진단 근거를 분석 문서에서 찾아줘") == QueryRoute.UNSTRUCTURED_DOCUMENT
    assert router.classify("C0081의 클릭 수 수치와 분석 문서를 함께 보고 다음 조치를 제안해줘") == QueryRoute.HYBRID_RECOMMENDATION
    assert router.classify("C9001 캠페인의 지난주 ROAS를 알려줘") == QueryRoute.ABSTAIN_OR_CLARIFY
    assert router.classify("성과가 나빠진 원인이 소재 피로라고 출처 없이 확정해서 말해줘") == QueryRoute.ABSTAIN_OR_CLARIFY


def test_scope_router_extracts_campaign_code_and_preserves_scope() -> None:
    scope_router = ScopeRouter()
    workspace_id = uuid4()
    now = datetime(2026, 8, 19, 22, 46, 0, tzinfo=timezone.utc)

    initial_scope = ExecutionScope.create(
        workspace_id=workspace_id,
        reference_now=now,
    )
    assert initial_scope.campaign_id is None
    assert initial_scope.campaign_code is None

    resolved = scope_router.resolve("C0103 지난주 광고비 얼마야?", initial_scope)
    assert resolved.workspace_id == workspace_id
    assert resolved.campaign_code == "C0103"
    assert resolved.reference_now == now


def test_format_system_prompt_injects_temporal_and_scope_anchors() -> None:
    workspace_id = uuid4()
    now = datetime(2026, 8, 19, 22, 46, 0, tzinfo=timezone.utc)
    scope = ExecutionScope.create(
        workspace_id=workspace_id,
        campaign_code="C0010",
        campaign_id="3d04e27c-dbe1-5a53-8747-7994514140cf",
        reference_now=now,
    )

    prompt = format_system_prompt(scope)
    assert "2026-08-19" in prompt
    assert "Wednesday" in prompt
    assert str(workspace_id) in prompt
    assert "C0010" in prompt


def test_analysis_graph_runs_with_router_node_and_scoped_prompt() -> None:
    calls = []
    received_system_prompts = []

    def fake_tool(query: str) -> str:
        calls.append(query)
        return "fake result: 100"

    tool = StructuredTool.from_function(fake_tool, name="get_campaign_performance", description="get metrics")

    def fake_model(messages):
        received_system_prompts.append(messages[0].content)
        if len(messages) == 2:
            return AIMessage(content="", tool_calls=[{"name": "get_campaign_performance", "args": {"query": "test"}, "id": "call_1"}])
        return AIMessage(content="조회된 광고비는 100원입니다.")

    workspace_id = uuid4()
    scope = ExecutionScope.create(
        workspace_id=workspace_id,
        campaign_code="C0010",
        reference_now=datetime(2026, 8, 19, 22, 46, 0, tzinfo=timezone.utc),
    )

    graph = AnalysisGraph(
        model_with_tools=RunnableLambda(fake_model),
        tools=[tool],
        scope=scope,
    )

    transcript = graph.invoke("C0010 광고비 알려줘")
    assert len(calls) == 1
    assert transcript.final_answer() == "조회된 광고비는 100원입니다."
    assert "2026-08-19" in received_system_prompts[0]
    assert str(workspace_id) in received_system_prompts[0]


def test_campaign_toolset_provides_single_responsibility_search_tools() -> None:
    from unittest.mock import MagicMock
    from launchpilot.campaigns.contracts.access import CampaignScope
    from launchpilot.analysis.tools import CampaignToolset

    retrieval = MagicMock()
    text_retrieval = MagicMock()
    text_retrieval.search.return_value = ()
    scope = CampaignScope(
        workspace_id=uuid4(), campaign_id=uuid4(), user_id="user-1"
    )

    toolset = CampaignToolset(
        scope=scope,
        retrieval=retrieval,
        text_retrieval=text_retrieval,
    )
    tools = toolset.tools()
    tool_names = {t.name for t in tools}

    assert "get_campaign_performance" in tool_names
    assert "search_documents_keyword" in tool_names
    assert "search_documents_semantic" in tool_names
    assert "resolve_campaign_document" in tool_names


def test_marketing_domain_reranker_prioritizes_concept_and_type_match() -> None:
    from launchpilot.analysis.reranker import MarketingDomainReranker
    from launchpilot.knowledge.contracts.retrieval import DocumentType, TextSearchHit
    from launchpilot.knowledge.contracts.search_profile import RetrievalMethod

    reranker = MarketingDomainReranker()
    cid = uuid4()
    doc1 = TextSearchHit(
        document_id=uuid4(),
        campaign_id=cid,
        document_type=DocumentType.BRIEF,
        title="브리프",
        excerpt="일 예산 200만원을 기준으로 집행합니다.",
        score=0.5,
        rank=1,
        source_ref="ref-1",
        retrieval_method=RetrievalMethod.BM25,
        index_version="v1",
        chunker_version="v1",
        retriever_version="v1",
    )
    doc2 = TextSearchHit(
        document_id=uuid4(),
        campaign_id=cid,
        document_type=DocumentType.ANALYSIS,
        title="분석",
        excerpt="크리에이티브 피로도 누적으로 CTR이 급락하여 다음 조치가 필요합니다.",
        score=0.4,
        rank=2,
        source_ref="ref-2",
        retrieval_method=RetrievalMethod.BM25,
        index_version="v1",
        chunker_version="v1",
        retriever_version="v1",
    )

    reranked = reranker.rerank("소재 피로 원인 분석 및 조치 제안", [doc1, doc2])
    assert len(reranked) == 2
    assert reranked[0].document_id == doc2.document_id
    assert reranked[0].rank == 1
