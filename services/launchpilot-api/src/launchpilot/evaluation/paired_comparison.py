from __future__ import annotations

import argparse
import json
import random
import statistics
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from launchpilot.evaluation.contracts import TrialRunResult


class Transition(StrEnum):
    NEWLY_SOLVED = "newly_solved"
    REGRESSION = "regression"
    PASS_TO_PASS = "pass_to_pass"
    FAIL_TO_FAIL = "fail_to_fail"


class PairwiseMetric(StrEnum):
    REQUIRED_FACT_COVERAGE = "required_fact_coverage"
    GROUNDEDNESS = "groundedness"
    ANSWER_RELEVANCE = "answer_relevance"


class ComparisonConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    minimum_trials_per_case: int = Field(default=1, ge=1)
    pass_rate_threshold: float = Field(default=0.5, gt=0.0, le=1.0)
    pairwise_metric: PairwiseMetric = PairwiseMetric.REQUIRED_FACT_COVERAGE
    tie_tolerance: float = Field(default=0.01, ge=0.0)
    bootstrap_samples: int = Field(default=2000, ge=100)
    bootstrap_seed: int = 17
    require_control_match: bool = True


class CaseAggregate(BaseModel):
    model_config = ConfigDict(frozen=True)

    query_id: str
    spec_id: str
    spec_version: str
    trial_count: int
    success_rate: float
    all_trials_passed: bool
    required_fact_coverage: float
    groundedness: float | None
    answer_relevance: float | None
    mean_latency_ms: float
    mean_cost_usd: float | None
    mean_tool_calls: float


class PairedCaseComparison(BaseModel):
    model_config = ConfigDict(frozen=True)

    query_id: str
    transition: Transition
    baseline: CaseAggregate
    candidate: CaseAggregate
    fact_coverage_delta: float
    groundedness_delta: float | None
    answer_relevance_delta: float | None
    latency_delta_ms: float
    cost_delta_usd: float | None
    tool_call_delta: float


class BootstrapInterval(BaseModel):
    model_config = ConfigDict(frozen=True)

    mean_delta: float
    lower_95: float
    upper_95: float
    samples: int


class SystemAggregate(BaseModel):
    model_config = ConfigDict(frozen=True)

    system_version: str
    case_count: int
    trial_count: int
    trial_success_rate: float
    mean_case_success_rate: float
    all_trials_passed_case_rate: float
    mean_required_fact_coverage: float
    mean_groundedness: float | None
    mean_answer_relevance: float | None
    mean_latency_ms: float
    mean_cost_usd: float | None
    cost_per_successful_trial_usd: float | None
    latency_per_successful_trial_ms: float | None
    mean_tool_calls: float


class PairedComparisonSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    baseline: SystemAggregate
    candidate: SystemAggregate
    matched_cases: int
    baseline_only_cases: tuple[str, ...]
    candidate_only_cases: tuple[str, ...]
    insufficient_trial_cases: tuple[str, ...]
    newly_solved: int
    regressions: int
    net_gain: int
    pass_to_pass: int
    fail_to_fail: int
    pairwise_wins: int
    pairwise_losses: int
    pairwise_ties: int
    pairwise_metric: PairwiseMetric
    fact_coverage_delta: BootstrapInterval
    mean_groundedness_delta: float | None
    mean_answer_relevance_delta: float | None
    mean_latency_delta_ms: float
    mean_cost_delta_usd: float | None
    mean_tool_call_delta: float
    cases: tuple[PairedCaseComparison, ...]


def compare_systems(
    baseline_trials: Sequence[TrialRunResult],
    candidate_trials: Sequence[TrialRunResult],
    *,
    config: ComparisonConfig | None = None,
) -> PairedComparisonSummary:
    settings = config or ComparisonConfig()
    baseline_version = _single_system_version(baseline_trials, "baseline")
    candidate_version = _single_system_version(candidate_trials, "candidate")
    baseline_by_case = _by_query(baseline_trials)
    candidate_by_case = _by_query(candidate_trials)
    baseline_ids = set(baseline_by_case)
    candidate_ids = set(candidate_by_case)
    common_ids = sorted(baseline_ids & candidate_ids)

    insufficient = tuple(
        query_id
        for query_id in common_ids
        if len(baseline_by_case[query_id]) < settings.minimum_trials_per_case
        or len(candidate_by_case[query_id]) < settings.minimum_trials_per_case
    )
    eligible_ids = [query_id for query_id in common_ids if query_id not in insufficient]
    if not eligible_ids:
        raise ValueError("no paired cases satisfy the minimum trial requirement")

    if settings.require_control_match:
        _validate_controls(
            baseline_by_case,
            candidate_by_case,
            eligible_ids,
        )

    comparisons = tuple(
        _compare_case(
            _aggregate_case(query_id, baseline_by_case[query_id]),
            _aggregate_case(query_id, candidate_by_case[query_id]),
            pass_rate_threshold=settings.pass_rate_threshold,
        )
        for query_id in eligible_ids
    )
    transitions = [case.transition for case in comparisons]
    wins, losses, ties = _win_loss_tie(comparisons, settings)
    fact_deltas = [case.fact_coverage_delta for case in comparisons]

    return PairedComparisonSummary(
        baseline=_aggregate_system(
            baseline_version,
            [
                trial
                for query_id in eligible_ids
                for trial in baseline_by_case[query_id]
            ],
        ),
        candidate=_aggregate_system(
            candidate_version,
            [
                trial
                for query_id in eligible_ids
                for trial in candidate_by_case[query_id]
            ],
        ),
        matched_cases=len(comparisons),
        baseline_only_cases=tuple(sorted(baseline_ids - candidate_ids)),
        candidate_only_cases=tuple(sorted(candidate_ids - baseline_ids)),
        insufficient_trial_cases=insufficient,
        newly_solved=transitions.count(Transition.NEWLY_SOLVED),
        regressions=transitions.count(Transition.REGRESSION),
        net_gain=(
            transitions.count(Transition.NEWLY_SOLVED)
            - transitions.count(Transition.REGRESSION)
        ),
        pass_to_pass=transitions.count(Transition.PASS_TO_PASS),
        fail_to_fail=transitions.count(Transition.FAIL_TO_FAIL),
        pairwise_wins=wins,
        pairwise_losses=losses,
        pairwise_ties=ties,
        pairwise_metric=settings.pairwise_metric,
        fact_coverage_delta=_bootstrap_interval(
            fact_deltas,
            samples=settings.bootstrap_samples,
            seed=settings.bootstrap_seed,
        ),
        mean_groundedness_delta=_mean_optional(
            case.groundedness_delta for case in comparisons
        ),
        mean_answer_relevance_delta=_mean_optional(
            case.answer_relevance_delta for case in comparisons
        ),
        mean_latency_delta_ms=statistics.fmean(
            case.latency_delta_ms for case in comparisons
        ),
        mean_cost_delta_usd=_mean_optional(case.cost_delta_usd for case in comparisons),
        mean_tool_call_delta=statistics.fmean(
            case.tool_call_delta for case in comparisons
        ),
        cases=comparisons,
    )


def _single_system_version(trials: Sequence[TrialRunResult], label: str) -> str:
    versions = {trial.system_version for trial in trials}
    if not versions:
        raise ValueError(f"{label} run is empty")
    if len(versions) != 1:
        raise ValueError(
            f"{label} contains multiple system versions: {sorted(versions)}"
        )
    return next(iter(versions))


def _by_query(
    trials: Sequence[TrialRunResult],
) -> dict[str, list[TrialRunResult]]:
    output: dict[str, list[TrialRunResult]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for trial in trials:
        key = (trial.query_id, trial.trial_id)
        if key in seen:
            raise ValueError(f"duplicate query/trial pair: {key}")
        seen.add(key)
        output[trial.query_id].append(trial)
    return dict(output)


def _validate_controls(
    baseline: dict[str, list[TrialRunResult]],
    candidate: dict[str, list[TrialRunResult]],
    query_ids: Sequence[str],
) -> None:
    violations = []
    for query_id in query_ids:
        base_trials = baseline[query_id]
        candidate_trials = candidate[query_id]
        base_spec = {(trial.spec_id, trial.spec_version) for trial in base_trials}
        candidate_spec = {
            (trial.spec_id, trial.spec_version) for trial in candidate_trials
        }
        if len(base_spec) != 1 or base_spec != candidate_spec:
            violations.append(f"{query_id}: eval specification differs")
        for field in ("corpus", "model", "prompt"):
            base_values = {getattr(trial.versions, field) for trial in base_trials}
            candidate_values = {
                getattr(trial.versions, field) for trial in candidate_trials
            }
            if len(base_values) != 1 or base_values != candidate_values:
                violations.append(f"{query_id}: controlled field differs: {field}")
    if violations:
        raise ValueError("uncontrolled paired experiment: " + "; ".join(violations))


def _aggregate_case(
    query_id: str,
    trials: Sequence[TrialRunResult],
) -> CaseAggregate:
    spec_pairs = {(trial.spec_id, trial.spec_version) for trial in trials}
    if len(spec_pairs) != 1:
        raise ValueError(f"{query_id}: trials use multiple eval specifications")
    spec_id, spec_version = next(iter(spec_pairs))
    successes = [trial.outcome.task_success for trial in trials]
    costs = [trial.efficiency.cost_usd for trial in trials]
    return CaseAggregate(
        query_id=query_id,
        spec_id=spec_id,
        spec_version=spec_version,
        trial_count=len(trials),
        success_rate=sum(successes) / len(trials),
        all_trials_passed=all(successes),
        required_fact_coverage=statistics.fmean(
            trial.outcome.required_fact_coverage for trial in trials
        ),
        groundedness=_mean_optional(trial.outcome.groundedness for trial in trials),
        answer_relevance=_mean_optional(
            trial.outcome.answer_relevance for trial in trials
        ),
        mean_latency_ms=statistics.fmean(
            trial.efficiency.end_to_end_latency_ms for trial in trials
        ),
        mean_cost_usd=_mean_optional(costs),
        mean_tool_calls=statistics.fmean(len(trial.tool_trace) for trial in trials),
    )


def _compare_case(
    baseline: CaseAggregate,
    candidate: CaseAggregate,
    *,
    pass_rate_threshold: float,
) -> PairedCaseComparison:
    base_pass = baseline.success_rate >= pass_rate_threshold
    candidate_pass = candidate.success_rate >= pass_rate_threshold
    if not base_pass and candidate_pass:
        transition = Transition.NEWLY_SOLVED
    elif base_pass and not candidate_pass:
        transition = Transition.REGRESSION
    elif base_pass and candidate_pass:
        transition = Transition.PASS_TO_PASS
    else:
        transition = Transition.FAIL_TO_FAIL
    return PairedCaseComparison(
        query_id=baseline.query_id,
        transition=transition,
        baseline=baseline,
        candidate=candidate,
        fact_coverage_delta=(
            candidate.required_fact_coverage - baseline.required_fact_coverage
        ),
        groundedness_delta=_optional_delta(
            baseline.groundedness, candidate.groundedness
        ),
        answer_relevance_delta=_optional_delta(
            baseline.answer_relevance, candidate.answer_relevance
        ),
        latency_delta_ms=candidate.mean_latency_ms - baseline.mean_latency_ms,
        cost_delta_usd=_optional_delta(baseline.mean_cost_usd, candidate.mean_cost_usd),
        tool_call_delta=candidate.mean_tool_calls - baseline.mean_tool_calls,
    )


def _aggregate_system(
    system_version: str,
    trials: Sequence[TrialRunResult],
) -> SystemAggregate:
    cases = [
        _aggregate_case(query_id, items)
        for query_id, items in _by_query(trials).items()
    ]
    successes = sum(trial.outcome.task_success for trial in trials)
    costs = [trial.efficiency.cost_usd for trial in trials]
    total_cost = sum(value for value in costs if value is not None)
    has_complete_cost = all(value is not None for value in costs)
    total_latency = sum(trial.efficiency.end_to_end_latency_ms for trial in trials)
    return SystemAggregate(
        system_version=system_version,
        case_count=len(cases),
        trial_count=len(trials),
        trial_success_rate=successes / len(trials),
        mean_case_success_rate=statistics.fmean(case.success_rate for case in cases),
        all_trials_passed_case_rate=(
            sum(case.all_trials_passed for case in cases) / len(cases)
        ),
        mean_required_fact_coverage=statistics.fmean(
            trial.outcome.required_fact_coverage for trial in trials
        ),
        mean_groundedness=_mean_optional(
            trial.outcome.groundedness for trial in trials
        ),
        mean_answer_relevance=_mean_optional(
            trial.outcome.answer_relevance for trial in trials
        ),
        mean_latency_ms=statistics.fmean(
            trial.efficiency.end_to_end_latency_ms for trial in trials
        ),
        mean_cost_usd=_mean_optional(costs),
        cost_per_successful_trial_usd=(
            total_cost / successes if has_complete_cost and successes else None
        ),
        latency_per_successful_trial_ms=(
            total_latency / successes if successes else None
        ),
        mean_tool_calls=statistics.fmean(len(trial.tool_trace) for trial in trials),
    )


def _win_loss_tie(
    comparisons: Sequence[PairedCaseComparison],
    config: ComparisonConfig,
) -> tuple[int, int, int]:
    metric: Callable[[CaseAggregate], float | None] = lambda case: getattr(
        case, config.pairwise_metric.value
    )
    wins = losses = ties = 0
    for comparison in comparisons:
        baseline = metric(comparison.baseline)
        candidate = metric(comparison.candidate)
        if baseline is None or candidate is None:
            ties += 1
            continue
        delta = candidate - baseline
        if delta > config.tie_tolerance:
            wins += 1
        elif delta < -config.tie_tolerance:
            losses += 1
        else:
            ties += 1
    return wins, losses, ties


def _bootstrap_interval(
    values: Sequence[float],
    *,
    samples: int,
    seed: int,
) -> BootstrapInterval:
    rng = random.Random(seed)
    sample_size = len(values)
    means = sorted(
        statistics.fmean(values[rng.randrange(sample_size)] for _ in range(sample_size))
        for _ in range(samples)
    )
    lower_index = int(0.025 * (samples - 1))
    upper_index = int(0.975 * (samples - 1))
    return BootstrapInterval(
        mean_delta=statistics.fmean(values),
        lower_95=means[lower_index],
        upper_95=means[upper_index],
        samples=samples,
    )


def _optional_delta(baseline: float | None, candidate: float | None) -> float | None:
    if baseline is None or candidate is None:
        return None
    return candidate - baseline


def _mean_optional(values: Iterable[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return statistics.fmean(present) if present else None


def load_trial_results(path: Path) -> tuple[TrialRunResult, ...]:
    return tuple(
        TrialRunResult.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare two architecture runs on paired query trials."
    )
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--minimum-trials", type=int, default=1)
    parser.add_argument("--pass-rate", type=float, default=0.5)
    parser.add_argument(
        "--pairwise-metric",
        choices=[metric.value for metric in PairwiseMetric],
        default=PairwiseMetric.REQUIRED_FACT_COVERAGE.value,
    )
    args = parser.parse_args()
    summary = compare_systems(
        load_trial_results(args.baseline),
        load_trial_results(args.candidate),
        config=ComparisonConfig(
            minimum_trials_per_case=args.minimum_trials,
            pass_rate_threshold=args.pass_rate,
            pairwise_metric=PairwiseMetric(args.pairwise_metric),
        ),
    )
    payload = json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)


if __name__ == "__main__":
    main()
