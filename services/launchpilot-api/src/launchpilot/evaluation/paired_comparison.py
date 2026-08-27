from __future__ import annotations

import argparse
import json
import random
import statistics
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from launchpilot.evaluation.contracts import TrialRunResult, TrialStatus


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
    tie_tolerance: float = Field(default=0.01, ge=0.0, le=1.0)
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
    groundedness_scored_trials: int
    answer_relevance: float | None
    answer_relevance_scored_trials: int
    mean_latency_ms: float
    mean_cost_usd: float | None
    mean_tool_calls: float | None


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
    tool_call_delta: float | None


class BootstrapInterval(BaseModel):
    model_config = ConfigDict(frozen=True)

    mean_delta: float
    lower_95: float
    upper_95: float
    samples: int
    method: str
    resampling_unit: str
    independent_cluster_count: int = Field(ge=1)


class SystemAggregate(BaseModel):
    model_config = ConfigDict(frozen=True)

    system_version: str
    case_count: int
    trial_count: int
    completed_trial_rate: float
    system_failure_rate: float
    timeout_rate: float
    trial_success_rate: float
    mean_case_success_rate: float
    all_trials_passed_case_rate: float
    mean_required_fact_coverage: float
    mean_groundedness: float | None
    groundedness_scored_trial_rate: float
    mean_answer_relevance: float | None
    answer_relevance_scored_trial_rate: float
    answer_bearing_evidence_retrieval_rate: float | None
    answer_bearing_evidence_scored_trial_rate: float
    mean_known_relevant_recall_at_k: float | None
    known_relevant_recall_scored_trial_rate: float
    known_relevant_recall_cutoff_k: int | None
    mean_latency_ms: float
    latency_p95_ms: float
    latency_stddev_ms: float
    mean_cost_usd: float | None
    cost_stddev_usd: float | None
    cost_per_successful_trial_usd: float | None
    latency_per_successful_trial_ms: float | None
    mean_tool_calls: float | None
    tool_trace_complete_rate: float
    efficiency_telemetry_complete_rate: float


class PairedComparisonSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    config: ComparisonConfig
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
    pairwise_unscored: int
    pairwise_metric: PairwiseMetric
    task_success_rate_delta: BootstrapInterval
    fact_coverage_delta: BootstrapInterval
    mean_groundedness_delta: float | None
    groundedness_paired_cases: int
    mean_answer_relevance_delta: float | None
    answer_relevance_paired_cases: int
    answer_bearing_evidence_rate_delta: float | None
    known_relevant_recall_at_k_delta: float | None
    mean_latency_delta_ms: float
    mean_cost_delta_usd: float | None
    mean_tool_call_delta: float | None
    cases: tuple[PairedCaseComparison, ...]


def compare_systems(
    baseline_trials: Sequence[TrialRunResult],
    candidate_trials: Sequence[TrialRunResult],
    *,
    config: ComparisonConfig | None = None,
    resampling_clusters: Mapping[str, str] | None = None,
) -> PairedComparisonSummary:
    settings = config or ComparisonConfig()
    harness_failures = [
        trial
        for trial in (*baseline_trials, *candidate_trials)
        if trial.status == TrialStatus.HARNESS_FAILED
    ]
    if harness_failures:
        raise ValueError("harness/grader failures must be resolved before comparison")
    baseline_version = _single_system_version(baseline_trials, "baseline")
    candidate_version = _single_system_version(candidate_trials, "candidate")
    if baseline_version == candidate_version:
        raise ValueError("baseline and candidate must be different system versions")
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
    if resampling_clusters is not None:
        missing_clusters = set(eligible_ids) - resampling_clusters.keys()
        if missing_clusters:
            raise ValueError(
                f"resampling clusters missing queries: {sorted(missing_clusters)}"
            )

    _validate_pairing(baseline_by_case, candidate_by_case, eligible_ids)
    if settings.require_control_match:
        _validate_controls(baseline_by_case, candidate_by_case, eligible_ids)

    comparisons = tuple(
        _compare_case(
            _aggregate_case(query_id, baseline_by_case[query_id]),
            _aggregate_case(query_id, candidate_by_case[query_id]),
            pass_rate_threshold=settings.pass_rate_threshold,
        )
        for query_id in eligible_ids
    )
    transitions = [case.transition for case in comparisons]
    wins, losses, ties, unscored = _win_loss_tie(comparisons, settings)
    baseline_aggregate = _aggregate_system(
        baseline_version,
        [
            trial
            for query_id in eligible_ids
            for trial in baseline_by_case[query_id]
        ],
    )
    candidate_aggregate = _aggregate_system(
        candidate_version,
        [
            trial
            for query_id in eligible_ids
            for trial in candidate_by_case[query_id]
        ],
    )

    return PairedComparisonSummary(
        config=settings,
        baseline=baseline_aggregate,
        candidate=candidate_aggregate,
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
        pairwise_unscored=unscored,
        pairwise_metric=settings.pairwise_metric,
        task_success_rate_delta=_hierarchical_bootstrap_interval(
            baseline_by_case,
            candidate_by_case,
            eligible_ids,
            metric=lambda trial: float(trial.outcome.task_success),
            cluster_by_query=resampling_clusters,
            samples=settings.bootstrap_samples,
            seed=settings.bootstrap_seed,
        ),
        fact_coverage_delta=_hierarchical_bootstrap_interval(
            baseline_by_case,
            candidate_by_case,
            eligible_ids,
            metric=lambda trial: trial.outcome.required_fact_coverage,
            cluster_by_query=resampling_clusters,
            samples=settings.bootstrap_samples,
            seed=settings.bootstrap_seed + 1,
        ),
        mean_groundedness_delta=_mean_optional(
            case.groundedness_delta for case in comparisons
        ),
        groundedness_paired_cases=sum(
            case.groundedness_delta is not None for case in comparisons
        ),
        mean_answer_relevance_delta=_mean_optional(
            case.answer_relevance_delta for case in comparisons
        ),
        answer_relevance_paired_cases=sum(
            case.answer_relevance_delta is not None for case in comparisons
        ),
        answer_bearing_evidence_rate_delta=_optional_delta(
            baseline_aggregate.answer_bearing_evidence_retrieval_rate,
            candidate_aggregate.answer_bearing_evidence_retrieval_rate,
        ),
        known_relevant_recall_at_k_delta=(
            _optional_delta(
                baseline_aggregate.mean_known_relevant_recall_at_k,
                candidate_aggregate.mean_known_relevant_recall_at_k,
            )
            if baseline_aggregate.known_relevant_recall_cutoff_k
            == candidate_aggregate.known_relevant_recall_cutoff_k
            else None
        ),
        mean_latency_delta_ms=statistics.fmean(
            case.latency_delta_ms for case in comparisons
        ),
        mean_cost_delta_usd=_mean_if_complete(
            [case.cost_delta_usd for case in comparisons]
        ),
        mean_tool_call_delta=_mean_if_complete(
            [case.tool_call_delta for case in comparisons]
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
        for field in ("corpus", "model", "prompt"):
            base_values = {getattr(trial.versions, field) for trial in base_trials}
            candidate_values = {
                getattr(trial.versions, field) for trial in candidate_trials
            }
            if len(base_values) != 1 or base_values != candidate_values:
                violations.append(f"{query_id}: controlled field differs: {field}")
    if violations:
        raise ValueError("uncontrolled paired experiment: " + "; ".join(violations))


def _validate_pairing(
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
        base_trial_keys = {
            (trial.trial_id, trial.requested_seed) for trial in base_trials
        }
        candidate_trial_keys = {
            (trial.trial_id, trial.requested_seed) for trial in candidate_trials
        }
        if base_trial_keys != candidate_trial_keys:
            violations.append(f"{query_id}: paired trial ids/seeds differ")
    if violations:
        raise ValueError("invalid paired experiment: " + "; ".join(violations))


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
    groundedness_values = [trial.outcome.groundedness for trial in trials]
    answer_relevance_values = [trial.outcome.answer_relevance for trial in trials]
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
        groundedness=_mean_optional(groundedness_values),
        groundedness_scored_trials=sum(
            value is not None for value in groundedness_values
        ),
        answer_relevance=_mean_optional(answer_relevance_values),
        answer_relevance_scored_trials=sum(
            value is not None for value in answer_relevance_values
        ),
        mean_latency_ms=statistics.fmean(
            trial.efficiency.end_to_end_latency_ms for trial in trials
        ),
        mean_cost_usd=_mean_if_complete(costs),
        mean_tool_calls=(
            statistics.fmean(len(trial.tool_trace) for trial in trials)
            if all(trial.tool_trace_complete for trial in trials)
            else None
        ),
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
        tool_call_delta=_optional_delta(
            baseline.mean_tool_calls, candidate.mean_tool_calls
        ),
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
    present_costs = [value for value in costs if value is not None]
    latencies = [trial.efficiency.end_to_end_latency_ms for trial in trials]
    groundedness_values = [trial.outcome.groundedness for trial in trials]
    answer_relevance_values = [trial.outcome.answer_relevance for trial in trials]
    answer_bearing_values = [
        trial.retrieval.answer_bearing_evidence_retrieved for trial in trials
    ]
    recall_trials = [
        trial
        for trial in trials
        if trial.retrieval.known_relevant_recall_at_k is not None
    ]
    recall_cutoffs = {trial.retrieval.cutoff_k for trial in recall_trials}
    recall_is_comparable = len(recall_cutoffs) == 1
    total_cost = sum(value for value in costs if value is not None)
    has_complete_cost = all(value is not None for value in costs)
    total_latency = sum(trial.efficiency.end_to_end_latency_ms for trial in trials)
    return SystemAggregate(
        system_version=system_version,
        case_count=len(cases),
        trial_count=len(trials),
        completed_trial_rate=(
            sum(trial.status == TrialStatus.COMPLETED for trial in trials)
            / len(trials)
        ),
        system_failure_rate=(
            sum(trial.status == TrialStatus.SYSTEM_FAILED for trial in trials)
            / len(trials)
        ),
        timeout_rate=(
            sum(trial.status == TrialStatus.TIMED_OUT for trial in trials)
            / len(trials)
        ),
        trial_success_rate=successes / len(trials),
        mean_case_success_rate=statistics.fmean(case.success_rate for case in cases),
        all_trials_passed_case_rate=(
            sum(case.all_trials_passed for case in cases) / len(cases)
        ),
        mean_required_fact_coverage=statistics.fmean(
            trial.outcome.required_fact_coverage for trial in trials
        ),
        mean_groundedness=_mean_optional(groundedness_values),
        groundedness_scored_trial_rate=(
            sum(value is not None for value in groundedness_values) / len(trials)
        ),
        mean_answer_relevance=_mean_optional(answer_relevance_values),
        answer_relevance_scored_trial_rate=(
            sum(value is not None for value in answer_relevance_values) / len(trials)
        ),
        answer_bearing_evidence_retrieval_rate=_mean_optional(
            float(value) if value is not None else None
            for value in answer_bearing_values
        ),
        answer_bearing_evidence_scored_trial_rate=(
            sum(value is not None for value in answer_bearing_values) / len(trials)
        ),
        mean_known_relevant_recall_at_k=(
            statistics.fmean(
                trial.retrieval.known_relevant_recall_at_k
                for trial in recall_trials
                if trial.retrieval.known_relevant_recall_at_k is not None
            )
            if recall_trials and recall_is_comparable
            else None
        ),
        known_relevant_recall_scored_trial_rate=len(recall_trials) / len(trials),
        known_relevant_recall_cutoff_k=(
            next(iter(recall_cutoffs))
            if recall_trials and recall_is_comparable
            else None
        ),
        mean_latency_ms=statistics.fmean(latencies),
        latency_p95_ms=_percentile(latencies, 0.95),
        latency_stddev_ms=statistics.pstdev(latencies),
        mean_cost_usd=_mean_if_complete(costs),
        cost_stddev_usd=(
            statistics.pstdev(present_costs) if has_complete_cost else None
        ),
        cost_per_successful_trial_usd=(
            total_cost / successes if has_complete_cost and successes else None
        ),
        latency_per_successful_trial_ms=(
            total_latency / successes if successes else None
        ),
        mean_tool_calls=(
            statistics.fmean(len(trial.tool_trace) for trial in trials)
            if all(trial.tool_trace_complete for trial in trials)
            else None
        ),
        tool_trace_complete_rate=(
            sum(trial.tool_trace_complete for trial in trials) / len(trials)
        ),
        efficiency_telemetry_complete_rate=(
            sum(trial.efficiency.telemetry_complete for trial in trials) / len(trials)
        ),
    )


def _win_loss_tie(
    comparisons: Sequence[PairedCaseComparison],
    config: ComparisonConfig,
) -> tuple[int, int, int, int]:
    metric: Callable[[CaseAggregate], float | None] = lambda case: getattr(
        case, config.pairwise_metric.value
    )
    wins = losses = ties = unscored = 0
    for comparison in comparisons:
        baseline = metric(comparison.baseline)
        candidate = metric(comparison.candidate)
        if baseline is None or candidate is None:
            unscored += 1
            continue
        delta = candidate - baseline
        if delta > config.tie_tolerance:
            wins += 1
        elif delta < -config.tie_tolerance:
            losses += 1
        else:
            ties += 1
    return wins, losses, ties, unscored


def _hierarchical_bootstrap_interval(
    baseline: dict[str, list[TrialRunResult]],
    candidate: dict[str, list[TrialRunResult]],
    query_ids: Sequence[str],
    *,
    metric: Callable[[TrialRunResult], float],
    cluster_by_query: Mapping[str, str] | None,
    samples: int,
    seed: int,
) -> BootstrapInterval:
    rng = random.Random(seed)
    deltas_by_query: dict[str, tuple[float, ...]] = {}
    for query_id in query_ids:
        baseline_by_trial = {
            (trial.trial_id, trial.requested_seed): trial
            for trial in baseline[query_id]
        }
        candidate_by_trial = {
            (trial.trial_id, trial.requested_seed): trial
            for trial in candidate[query_id]
        }
        deltas_by_query[query_id] = tuple(
            metric(candidate_by_trial[key]) - metric(baseline_by_trial[key])
            for key in sorted(baseline_by_trial)
        )

    queries_by_cluster: dict[str, list[str]] = defaultdict(list)
    for query_id in query_ids:
        cluster_id = (
            cluster_by_query[query_id]
            if cluster_by_query is not None
            else f"query:{query_id}"
        )
        queries_by_cluster[cluster_id].append(query_id)
    clusters = tuple(sorted(queries_by_cluster))
    cluster_count = len(clusters)
    means = sorted(
        statistics.fmean(
            statistics.fmean(
                deltas_by_query[query_id][
                    rng.randrange(len(deltas_by_query[query_id]))
                ]
                for _ in range(len(deltas_by_query[query_id]))
            )
            for query_id in (
                query_id
                for _ in range(cluster_count)
                for query_id in queries_by_cluster[
                    clusters[rng.randrange(cluster_count)]
                ]
            )
        )
        for _ in range(samples)
    )
    lower_index = int(0.025 * (samples - 1))
    upper_index = int(0.975 * (samples - 1))
    return BootstrapInterval(
        mean_delta=statistics.fmean(
            statistics.fmean(deltas) for deltas in deltas_by_query.values()
        ),
        lower_95=means[lower_index],
        upper_95=means[upper_index],
        samples=samples,
        method=(
            "paired_cluster_hierarchical_bootstrap"
            if cluster_by_query is not None
            else "paired_hierarchical_bootstrap"
        ),
        resampling_unit=(
            "leakage_cluster_then_matched_trial_pair"
            if cluster_by_query is not None
            else "query_then_matched_trial_pair"
        ),
        independent_cluster_count=cluster_count,
    )


def _optional_delta(baseline: float | None, candidate: float | None) -> float | None:
    if baseline is None or candidate is None:
        return None
    return candidate - baseline


def _mean_optional(values: Iterable[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return statistics.fmean(present) if present else None


def _mean_if_complete(values: Sequence[float | None]) -> float | None:
    if not values or any(value is None for value in values):
        return None
    return statistics.fmean(value for value in values if value is not None)


def _percentile(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


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
