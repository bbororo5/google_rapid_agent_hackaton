from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from langchain_core.messages import AIMessage

from launchpilot.analysis.evidence import EvidenceCollector
from launchpilot.analysis.graph import AnalysisGraph
from launchpilot.analysis.scope import ExecutionScope


@dataclass(frozen=True)
class AgentCaseEvaluationResult:
    case_id: str
    query: str
    analysis_task: str
    answer_mode: str
    passed: bool
    tool_called: list[str]
    evidence_count: int
    final_answer: str
    failure_reason: str | None = None


@dataclass(frozen=True)
class AgentBenchmarkSummary:
    total_cases: int
    passed_cases: int
    accuracy: float
    task_breakdown: dict[str, dict[str, float]]
    tool_call_distribution: dict[str, int]
    interpretation: str = "legacy_smoke_pass_rate_not_answer_correctness"


class GoldenAgentEvaluator:
    """Legacy graph-plumbing smoke evaluator over Golden V2.

    This class does not grade required facts or grounding and its accuracy is
    not an answer-correctness metric. Architecture selection must use the
    Query/EvalSpecification/TrialRunResult pipeline instead.
    """

    def __init__(self, golden_root: Path) -> None:
        self._root = golden_root
        self._cases_path = golden_root / "queries" / "cases.jsonl"
        self._docs_path = golden_root / "corpus" / "documents.jsonl"
        self._metrics_path = golden_root / "corpus" / "metrics.jsonl"

    def load_cases(self) -> list[dict[str, Any]]:
        cases = []
        with open(self._cases_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    cases.append(json.loads(line))
        return cases

    def evaluate_case(
        self,
        case: dict[str, Any],
        graph: AnalysisGraph,
    ) -> AgentCaseEvaluationResult:
        query = case["query"]
        task = case.get("analysis_task", "unknown")
        answer_mode = case.get("answer_mode", "direct")
        # Execute the agent without treating a taxonomy label as routing truth.
        transcript = graph.invoke(query)
        tools_called = [
            tc["name"]
            for msg in transcript.messages
            if isinstance(msg, AIMessage) and msg.tool_calls
            for tc in msg.tool_calls
        ]

        # Collect process diagnostics independently from the smoke pass condition.
        collector = EvidenceCollector()
        evidence = collector.collect(transcript)
        final_text = transcript.final_answer()

        # Legacy smoke criterion only. Do not interpret this as answer correctness.
        passed = True
        failure_reason = None

        if answer_mode == "abstention":
            acceptable = case.get("acceptable_answers", [])
            has_abstention_phrase = any(
                phrase in final_text
                for phrase in (
                    *acceptable,
                    "직접 비교할 수 없습니다",
                    "확정할 수 없습니다",
                    "등록되어 있지 않습니다",
                )
            )
            if not has_abstention_phrase:
                passed = False
                failure_reason = "Legacy abstention smoke phrase was absent"
        else:
            if not final_text.strip():
                passed = False
                failure_reason = "Empty final response"

        return AgentCaseEvaluationResult(
            case_id=case["case_id"],
            query=query,
            analysis_task=task,
            answer_mode=answer_mode,
            passed=passed,
            tool_called=tools_called,
            evidence_count=len(evidence),
            final_answer=final_text,
            failure_reason=failure_reason,
        )

    def run_benchmark(
        self,
        graph_factory: Any,
        cases: list[dict[str, Any]] | None = None,
    ) -> AgentBenchmarkSummary:
        all_cases = cases or self.load_cases()
        eval_results: list[AgentCaseEvaluationResult] = []
        tool_counts: dict[str, int] = {}
        task_stats: dict[str, dict[str, int]] = {}

        for case in all_cases:
            scope_dict = case.get("scope", {})
            scope = ExecutionScope.create(
                workspace_id=UUID(scope_dict["workspace_id"])
                if "workspace_id" in scope_dict
                else UUID("eb430fc4-5d88-58d2-ab66-993692e20b58"),
                campaign_id=UUID(scope_dict["campaign_id"])
                if scope_dict.get("campaign_id")
                else None,
                campaign_code=scope_dict.get("campaign_ref"),
                reference_now=datetime(2026, 8, 19, 23, 50, 0, tzinfo=UTC),
            )
            graph = graph_factory(scope)
            res = self.evaluate_case(case, graph)
            eval_results.append(res)

            for t in res.tool_called:
                tool_counts[t] = tool_counts.get(t, 0) + 1

            task = res.analysis_task
            if task not in task_stats:
                task_stats[task] = {"total": 0, "passed": 0}
            task_stats[task]["total"] += 1
            if res.passed:
                task_stats[task]["passed"] += 1

        total = len(eval_results)
        passed_total = sum(1 for r in eval_results if r.passed)
        accuracy = passed_total / total if total > 0 else 0.0

        task_breakdown = {
            task: {
                "total": stats["total"],
                "passed": stats["passed"],
                "accuracy": stats["passed"] / stats["total"]
                if stats["total"] > 0
                else 0.0,
            }
            for task, stats in task_stats.items()
        }

        return AgentBenchmarkSummary(
            total_cases=total,
            passed_cases=passed_total,
            accuracy=accuracy,
            task_breakdown=task_breakdown,
            tool_call_distribution=tool_counts,
        )
