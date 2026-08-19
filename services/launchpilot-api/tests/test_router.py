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


def test_analysis_graph_runs_through_router_node() -> None:
    def fake_tool(query: str) -> str:
        return "fake result"

    tool = StructuredTool.from_function(fake_tool, name="fake_tool", description="fake")
    model = RunnableLambda(lambda msgs: AIMessage(content="분석 완료"))

    graph = AnalysisGraph(
        model_with_tools=model,
        tools=[tool],
    )

    transcript = graph.invoke("C0010 지난주 광고비 알려줘")
    assert transcript.final_answer() == "분석 완료"
