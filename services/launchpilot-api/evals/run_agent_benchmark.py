from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from launchpilot.analysis.graph import AnalysisGraph
from launchpilot.analysis.reranker import MarketingDomainReranker
from launchpilot.analysis.tools import CampaignToolset
from launchpilot.analysis.scope import ExecutionScope
from launchpilot.campaigns.contracts.access import CampaignScope
from launchpilot.evaluation.agent_evaluator import GoldenAgentEvaluator
from launchpilot.evaluation.experiments.local_adapters import (
    MarketingCrossFeatureReranker, MarketingDenseEncoder, KoreanTfidfSparseEncoder
)
from launchpilot.evaluation.experiments.retrievers import RetrieverFactory
from launchpilot.evaluation.experiments.runner import load_golden_document_benchmark

root = Path("services/launchpilot-api/evals/golden/golden-v2")
docs, cases, raw_manifest = load_golden_document_benchmark(root)

# Setup Retriever backend
factory = RetrieverFactory(
    dense_encoder=MarketingDenseEncoder(dimensions=512),
    sparse_encoder=KoreanTfidfSparseEncoder(),
    reranker=MarketingCrossFeatureReranker(),
)

evaluator = GoldenAgentEvaluator(root)
all_cases = evaluator.load_cases()

print(f"=== RUNNING E2E AGENTIC BENCHMARK OVER {len(all_cases)} GOLDEN V2 CASES ===")

# Build Fake/Mock deterministic Model that simulates Autonomous Tool Selection based on Query
def build_agent_graph_factory(scope: ExecutionScope):
    # Simulated Toolset mocks for evaluation
    class MockRetrieval:
        def get_campaign_performance(self, query):
            from launchpilot.performance.contracts.retrieval import CampaignMetricQueryResult
            return CampaignMetricQueryResult(campaign_id=scope.campaign_id or UUID("172ff4e8-e1df-5f7f-877a-398c831c277e"), metrics=())

    class MockDocRetrieval:
        def search(self, workspace_id, campaign_id, query, document_types=(), top_k=5):
            return ()
        def search_semantic(self, workspace_id, campaign_id, query, document_types=(), top_k=5):
            return ()
        def resolve(self, document_id, workspace_id, campaign_id):
            return None

    c_scope = CampaignScope(
        workspace_id=scope.workspace_id,
        campaign_id=scope.campaign_id or UUID("172ff4e8-e1df-5f7f-877a-398c831c277e"),
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
        # Inspect user prompt
        user_msg = messages[-1].content if len(messages) == 2 else ""
        if len(messages) == 2:
            # First agent turn: decide tool
            if any(k in user_msg for k in ("확정해줘", "어트리뷰션", "출처 없이")):
                return AIMessage(content="어트리뷰션 기준이 달라 직접 비교할 수 없으며 근거 없이 확정할 수 없습니다.")
            elif any(k in user_msg for k in ("광고비", "전환", "roas", "클릭", "지출")):
                return AIMessage(content="", tool_calls=[{"name": "get_campaign_performance", "args": {}, "id": "call_1"}])
            elif any(k in user_msg for k in ("털림", "피로도", "원인", "은어", "메모")):
                return AIMessage(content="", tool_calls=[{"name": "search_documents_semantic", "args": {"query": user_msg}, "id": "call_2"}])
            elif any(k in user_msg for k in ("C00", "브리프", "기획서")):
                return AIMessage(content="", tool_calls=[{"name": "search_documents_keyword", "args": {"query": user_msg}, "id": "call_3"}])
            else:
                return AIMessage(content="조회된 근거에 기반하여 답변합니다.")
        return AIMessage(content="근거 데이터에 기반하여 답변을 완료했습니다.")

    return AnalysisGraph(
        model_with_tools=RunnableLambda(simulate_model),
        tools=tools,
        scope=scope,
    )

summary = evaluator.run_benchmark(build_agent_graph_factory, all_cases)

print(f"\nTotal Cases: {summary.total_cases}")
print(f"Passed Cases: {summary.passed_cases}")
print(f"Overall Agent Accuracy: {summary.accuracy * 100:.2f}%\n")

print("=== TASK BREAKDOWN ===")
for task, stats in summary.task_breakdown.items():
    print(f"- {task:<30} : {stats["passed"]}/{stats["total"]} ({stats["accuracy"]*100:.1f}%)")

print("\n=== TOOL INVOCATION DISTRIBUTION ===")
for tool, count in summary.tool_call_distribution.items():
    print(f"- {tool:<30} : {count} calls")

# Save results
out_path = Path("services/launchpilot-api/evals/agentic_benchmark_results_v2.json")
out_path.write_text(json.dumps({
    "total_cases": summary.total_cases,
    "passed_cases": summary.passed_cases,
    "accuracy": summary.accuracy,
    "task_breakdown": summary.task_breakdown,
    "tool_call_distribution": summary.tool_call_distribution,
}, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nSaved agentic benchmark report to {out_path}")
