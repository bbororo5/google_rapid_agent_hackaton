from __future__ import annotations

from pathlib import Path
from uuid import UUID

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from launchpilot.analysis.graph import AnalysisGraph
from launchpilot.analysis.reranker import MarketingDomainReranker
from launchpilot.analysis.scope import ExecutionScope
from launchpilot.analysis.tools import CampaignToolset
from launchpilot.campaigns.contracts.access import CampaignScope
from launchpilot.evaluation.agent_evaluator import GoldenAgentEvaluator


def test_e2e_agentic_benchmark_golden_v2() -> None:
    root = Path("evals/golden/golden-v2")
    if not root.exists():
        root = Path("services/launchpilot-api/evals/golden/golden-v2")

    evaluator = GoldenAgentEvaluator(root)
    all_cases = evaluator.load_cases()
    assert len(all_cases) == 680

    def build_agent_graph_factory(scope: ExecutionScope):
        class MockRetrieval:
            def get_campaign_performance(self, query):
                from launchpilot.performance.contracts.retrieval import (
                    CampaignMetricQueryResult,
                )

                return CampaignMetricQueryResult(
                    campaign_id=scope.campaign_id
                    or UUID("172ff4e8-e1df-5f7f-877a-398c831c277e"),
                    metrics=(),
                )

        class MockDocRetrieval:
            def search(
                self, workspace_id, campaign_id, query, document_types=(), top_k=5
            ):
                return ()

            def search_semantic(
                self, workspace_id, campaign_id, query, document_types=(), top_k=5
            ):
                return ()

            def resolve(self, document_id, workspace_id, campaign_id):
                return None

        c_scope = CampaignScope(
            workspace_id=scope.workspace_id,
            campaign_id=scope.campaign_id
            or UUID("172ff4e8-e1df-5f7f-877a-398c831c277e"),
            user_id="eval-user",
        )
        toolset = CampaignToolset(
            scope=c_scope,
            retrieval=MockRetrieval(),
            text_retrieval=MockDocRetrieval(),
            reranker=MarketingDomainReranker(),
        )
        tools = toolset.tools()

        def simulate_model(messages):
            user_msg = messages[-1].content if len(messages) == 2 else ""
            if len(messages) == 2:
                if any(k in user_msg for k in ("확정해줘", "어트리뷰션")):
                    return AIMessage(
                        content="어트리뷰션 기준이 달라 직접 비교할 수 없습니다."
                    )
                elif any(
                    k in user_msg for k in ("광고비", "전환", "roas", "클릭", "지출")
                ):
                    return AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "get_campaign_performance",
                                "args": {},
                                "id": "call_1",
                            }
                        ],
                    )
                elif any(
                    k in user_msg for k in ("털림", "피로도", "원인", "은어", "메모")
                ):
                    return AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "search_documents_semantic",
                                "args": {"query": user_msg},
                                "id": "call_2",
                            }
                        ],
                    )
                elif any(k in user_msg for k in ("C00", "브리프", "기획서")):
                    return AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "search_documents_keyword",
                                "args": {"query": user_msg},
                                "id": "call_3",
                            }
                        ],
                    )
                else:
                    return AIMessage(content="조회된 근거에 기반하여 답변합니다.")
            return AIMessage(content="근거 데이터에 기반하여 답변을 완료했습니다.")

        return AnalysisGraph(
            model_with_tools=RunnableLambda(simulate_model),
            tools=tools,
            scope=scope,
        )

    # Test sample of 20 cases in unit test
    summary = evaluator.run_benchmark(build_agent_graph_factory, all_cases[:20])
    assert summary.total_cases == 20
    assert summary.interpretation == "legacy_smoke_pass_rate_not_answer_correctness"
    assert 0 < summary.passed_cases <= summary.total_cases
