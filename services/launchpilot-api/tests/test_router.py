from __future__ import annotations

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import StructuredTool

from launchpilot.analysis.graph import AnalysisGraph
from launchpilot.analysis.router import QueryRoute, QueryRouter


def test_query_router_classifies_core_profiles() -> None:
    router = QueryRouter()

    assert router.classify("C0010 캠페인의 지난주 ROAS를 알려줘") == QueryRoute.STRUCTURED_METRIC
    assert router.classify("C0010 캠페인의 소재 피로 진단 근거를 분석 문서에서 찾아줘") == QueryRoute.UNSTRUCTURED_DOCUMENT
    assert router.classify("C0081의 클릭 수 수치와 분석 문서를 함께 보고 다음 조치를 제안해줘") == QueryRoute.HYBRID_RECOMMENDATION
    assert router.classify("C9001 캠페인의 지난주 ROAS를 알려줘") == QueryRoute.ABSTAIN_OR_CLARIFY
    assert router.classify("성과가 나빠진 원인이 소재 피로라고 출처 없이 확정해서 말해줘") == QueryRoute.ABSTAIN_OR_CLARIFY


def test_pure_autonomous_react_graph_runs_tool_loop() -> None:
    calls = []

    def fake_tool(query: str) -> str:
        calls.append(query)
        return "fake result: 100"

    tool = StructuredTool.from_function(fake_tool, name="get_campaign_performance", description="get metrics")
    
    # Model that responds with tool call first, then answer
    def fake_model(messages):
        if len(messages) == 2:  # System + Human
            from langchain_core.messages import ToolCall
            return AIMessage(content="", tool_calls=[{"name": "get_campaign_performance", "args": {"query": "test"}, "id": "call_1"}])
        return AIMessage(content="조회된 광고비는 100원입니다.")

    graph = AnalysisGraph(
        model_with_tools=RunnableLambda(fake_model),
        tools=[tool],
    )

    transcript = graph.invoke("C0010 광고비 알려줘")
    assert len(calls) == 1
    assert transcript.final_answer() == "조회된 광고비는 100원입니다."
