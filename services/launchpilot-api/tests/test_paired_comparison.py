from __future__ import annotations

import pytest

from launchpilot.evaluation.contracts import (
    ArtifactVersions,
    EfficiencyObservation,
    OutcomeScores,
    ToolCallStatus,
    ToolCallTrace,
    TrialRunResult,
)
from launchpilot.evaluation.paired_comparison import (
    ComparisonConfig,
    Transition,
    compare_systems,
)


def _trial(
    system: str,
    query_id: str,
    trial_number: int,
    *,
    success: bool,
    fact_coverage: float,
    groundedness: float,
    relevance: float,
    latency_ms: float,
    cost_usd: float,
    tool_calls: int = 1,
    corpus: str = "corpus-v1",
) -> TrialRunResult:
    return TrialRunResult(
        run_id=f"run-{system}",
        system_version=system,
        query_id=query_id,
        spec_id=f"{query_id}.spec",
        spec_version="v1",
        trial_id=f"trial-{trial_number}",
        versions=ArtifactVersions(
            corpus=corpus,
            index=f"index-{system}",
            model="model-v1",
            prompt="prompt-v1",
            toolset=f"tools-{system}",
            code_commit=f"commit-{system}",
        ),
        final_answer="answer",
        outcome=OutcomeScores(
            task_success=success,
            required_fact_coverage=fact_coverage,
            groundedness=groundedness,
            answer_relevance=relevance,
            behavior_correct=success,
        ),
        tool_trace=tuple(
            ToolCallTrace(
                sequence=index + 1,
                tool_name=f"tool-{index + 1}",
                status=ToolCallStatus.SUCCEEDED,
                latency_ms=10,
            )
            for index in range(tool_calls)
        ),
        efficiency=EfficiencyObservation(
            end_to_end_latency_ms=latency_ms,
            input_tokens=100,
            output_tokens=50,
            cost_usd=cost_usd,
        ),
    )


def test_paired_transitions_quality_reliability_and_efficiency() -> None:
    baseline = [
        _trial(
            "v0",
            "q1",
            1,
            success=False,
            fact_coverage=0.2,
            groundedness=0.3,
            relevance=0.5,
            latency_ms=100,
            cost_usd=0.01,
        ),
        _trial(
            "v0",
            "q1",
            2,
            success=False,
            fact_coverage=0.2,
            groundedness=0.3,
            relevance=0.5,
            latency_ms=100,
            cost_usd=0.01,
        ),
        _trial(
            "v0",
            "q2",
            1,
            success=True,
            fact_coverage=1.0,
            groundedness=0.9,
            relevance=0.9,
            latency_ms=100,
            cost_usd=0.01,
        ),
        _trial(
            "v0",
            "q2",
            2,
            success=True,
            fact_coverage=1.0,
            groundedness=0.9,
            relevance=0.9,
            latency_ms=100,
            cost_usd=0.01,
        ),
        _trial(
            "v0",
            "q3",
            1,
            success=True,
            fact_coverage=0.8,
            groundedness=0.7,
            relevance=0.8,
            latency_ms=100,
            cost_usd=0.01,
        ),
        _trial(
            "v0",
            "q3",
            2,
            success=True,
            fact_coverage=0.8,
            groundedness=0.7,
            relevance=0.8,
            latency_ms=100,
            cost_usd=0.01,
        ),
        _trial(
            "v0",
            "q4",
            1,
            success=False,
            fact_coverage=0.0,
            groundedness=0.1,
            relevance=0.2,
            latency_ms=100,
            cost_usd=0.01,
        ),
        _trial(
            "v0",
            "q4",
            2,
            success=False,
            fact_coverage=0.0,
            groundedness=0.1,
            relevance=0.2,
            latency_ms=100,
            cost_usd=0.01,
        ),
    ]
    candidate = [
        _trial(
            "v1",
            "q1",
            1,
            success=True,
            fact_coverage=1.0,
            groundedness=0.9,
            relevance=0.9,
            latency_ms=140,
            cost_usd=0.02,
            tool_calls=2,
        ),
        _trial(
            "v1",
            "q1",
            2,
            success=True,
            fact_coverage=1.0,
            groundedness=0.9,
            relevance=0.9,
            latency_ms=140,
            cost_usd=0.02,
            tool_calls=2,
        ),
        _trial(
            "v1",
            "q2",
            1,
            success=False,
            fact_coverage=0.4,
            groundedness=0.5,
            relevance=0.6,
            latency_ms=140,
            cost_usd=0.02,
            tool_calls=2,
        ),
        _trial(
            "v1",
            "q2",
            2,
            success=False,
            fact_coverage=0.4,
            groundedness=0.5,
            relevance=0.6,
            latency_ms=140,
            cost_usd=0.02,
            tool_calls=2,
        ),
        _trial(
            "v1",
            "q3",
            1,
            success=True,
            fact_coverage=1.0,
            groundedness=0.95,
            relevance=0.9,
            latency_ms=140,
            cost_usd=0.02,
            tool_calls=2,
        ),
        _trial(
            "v1",
            "q3",
            2,
            success=True,
            fact_coverage=1.0,
            groundedness=0.95,
            relevance=0.9,
            latency_ms=140,
            cost_usd=0.02,
            tool_calls=2,
        ),
        _trial(
            "v1",
            "q4",
            1,
            success=False,
            fact_coverage=0.1,
            groundedness=0.2,
            relevance=0.3,
            latency_ms=140,
            cost_usd=0.02,
            tool_calls=2,
        ),
        _trial(
            "v1",
            "q4",
            2,
            success=False,
            fact_coverage=0.1,
            groundedness=0.2,
            relevance=0.3,
            latency_ms=140,
            cost_usd=0.02,
            tool_calls=2,
        ),
    ]

    summary = compare_systems(
        baseline,
        candidate,
        config=ComparisonConfig(minimum_trials_per_case=2, bootstrap_samples=200),
    )

    assert summary.matched_cases == 4
    assert summary.newly_solved == 1
    assert summary.regressions == 1
    assert summary.net_gain == 0
    assert summary.pass_to_pass == 1
    assert summary.fail_to_fail == 1
    assert summary.pairwise_wins == 3
    assert summary.pairwise_losses == 1
    assert summary.mean_latency_delta_ms == 40
    assert summary.mean_cost_delta_usd == pytest.approx(0.01)
    assert summary.mean_tool_call_delta == 1
    assert summary.baseline.trial_success_rate == 0.5
    assert summary.candidate.trial_success_rate == 0.5
    assert summary.baseline.all_trials_passed_case_rate == 0.5
    assert summary.candidate.cost_per_successful_trial_usd == pytest.approx(0.04)
    assert {case.query_id: case.transition for case in summary.cases} == {
        "q1": Transition.NEWLY_SOLVED,
        "q2": Transition.REGRESSION,
        "q3": Transition.PASS_TO_PASS,
        "q4": Transition.FAIL_TO_FAIL,
    }


def test_trial_success_rate_exposes_stochastic_reliability() -> None:
    baseline = [
        _trial(
            "v0",
            "q1",
            1,
            success=True,
            fact_coverage=1,
            groundedness=1,
            relevance=1,
            latency_ms=10,
            cost_usd=0.01,
        ),
        _trial(
            "v0",
            "q1",
            2,
            success=True,
            fact_coverage=1,
            groundedness=1,
            relevance=1,
            latency_ms=10,
            cost_usd=0.01,
        ),
        _trial(
            "v0",
            "q1",
            3,
            success=True,
            fact_coverage=1,
            groundedness=1,
            relevance=1,
            latency_ms=10,
            cost_usd=0.01,
        ),
    ]
    candidate = [
        _trial(
            "v1",
            "q1",
            1,
            success=True,
            fact_coverage=1,
            groundedness=1,
            relevance=1,
            latency_ms=10,
            cost_usd=0.01,
        ),
        _trial(
            "v1",
            "q1",
            2,
            success=True,
            fact_coverage=1,
            groundedness=1,
            relevance=1,
            latency_ms=10,
            cost_usd=0.01,
        ),
        _trial(
            "v1",
            "q1",
            3,
            success=False,
            fact_coverage=0,
            groundedness=0,
            relevance=0,
            latency_ms=10,
            cost_usd=0.01,
        ),
    ]

    summary = compare_systems(
        baseline,
        candidate,
        config=ComparisonConfig(
            minimum_trials_per_case=3,
            pass_rate_threshold=2 / 3,
            bootstrap_samples=100,
        ),
    )

    assert summary.pass_to_pass == 1
    assert summary.baseline.all_trials_passed_case_rate == 1.0
    assert summary.candidate.all_trials_passed_case_rate == 0.0
    assert summary.candidate.trial_success_rate == pytest.approx(2 / 3)


def test_uncontrolled_corpus_change_is_rejected() -> None:
    baseline = [
        _trial(
            "v0",
            "q1",
            1,
            success=True,
            fact_coverage=1,
            groundedness=1,
            relevance=1,
            latency_ms=10,
            cost_usd=0.01,
        )
    ]
    candidate = [
        _trial(
            "v1",
            "q1",
            1,
            success=True,
            fact_coverage=1,
            groundedness=1,
            relevance=1,
            latency_ms=10,
            cost_usd=0.01,
            corpus="corpus-v2",
        )
    ]

    with pytest.raises(ValueError, match="controlled field differs: corpus"):
        compare_systems(
            baseline,
            candidate,
            config=ComparisonConfig(bootstrap_samples=100),
        )
