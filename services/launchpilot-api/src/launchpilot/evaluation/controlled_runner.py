from __future__ import annotations

import hashlib
import json
import random
import re
import tempfile
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from launchpilot.evaluation.contracts import (
    ArtifactVersions,
    EfficiencyObservation,
    EvalSpecification,
    EvidenceJudgment,
    ExperimentCondition,
    GraderKind,
    OutcomeScores,
    QueryRecord,
    RetrievalDiagnostics,
    ReviewStatus,
    ToolCallTrace,
    TrialFailureStage,
    TrialRunResult,
    TrialStatus,
)
from launchpilot.evaluation.paired_comparison import (
    ComparisonConfig,
    PairedComparisonSummary,
    compare_systems,
)

_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_INTERVENTION_FIELDS = {"index", "toolset", "code_commit", "condition"}


class CachePolicy(StrEnum):
    SYSTEM_ISOLATED = "system_isolated"
    DISABLED = "disabled"
    SHARED_EXPERIMENTAL = "shared_experimental"


class WarmupPolicy(StrEnum):
    IDENTICAL_PER_SYSTEM = "identical_per_system"
    NONE = "none"


class SystemExecutionError(RuntimeError):
    """The system failed; this counts against production reliability."""


class SystemTimeoutError(SystemExecutionError):
    pass


class SystemConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True)

    system_version: str = Field(min_length=1, pattern=_SAFE_ID.pattern)
    versions: ArtifactVersions
    condition: ExperimentCondition = Field(
        default_factory=lambda: ExperimentCondition(name="agent_selected")
    )


class ArchitectureContrast(BaseModel):
    """A predeclared comparison and the fields intentionally changed."""

    model_config = ConfigDict(frozen=True)

    contrast_id: str = Field(min_length=1, pattern=_SAFE_ID.pattern)
    baseline_system_version: str = Field(min_length=1)
    candidate_system_version: str = Field(min_length=1)
    hypothesis: str = Field(min_length=1)
    intervention_fields: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_intervention_fields(self) -> ArchitectureContrast:
        invalid = set(self.intervention_fields) - _INTERVENTION_FIELDS
        if invalid:
            raise ValueError(f"unsupported intervention fields: {sorted(invalid)}")
        if len(self.intervention_fields) != len(set(self.intervention_fields)):
            raise ValueError("intervention_fields must be unique")
        if self.baseline_system_version == self.candidate_system_version:
            raise ValueError("a contrast requires two different systems")
        return self


class GraderProvenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    grader_id: str = Field(min_length=1)
    code_commit: str = Field(min_length=1)
    rubric_version: str = Field(min_length=1)
    model: str | None = None
    prompt_version: str | None = None
    calibration_version: str | None = None
    seed: int | None = Field(default=None, ge=0)
    compatible_spec_rubric_versions: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_rubric_versions(self) -> GraderProvenance:
        if len(self.compatible_spec_rubric_versions) != len(
            set(self.compatible_spec_rubric_versions)
        ):
            raise ValueError("compatible_spec_rubric_versions must be unique")
        if bool(self.model) != bool(self.prompt_version):
            raise ValueError("model and prompt_version must be declared together")
        return self


class EvaluationDatasetProvenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset_id: str = Field(min_length=1, pattern=_SAFE_ID.pattern)
    dataset_version: str = Field(min_length=1)
    artifact_uri: str = Field(min_length=1)
    source_artifact_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    selection_id: str = Field(min_length=1)


class ControlledExperimentPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1, pattern=_SAFE_ID.pattern)
    systems: tuple[SystemConfiguration, ...] = Field(min_length=2)
    contrasts: tuple[ArchitectureContrast, ...] = Field(min_length=1)
    evaluation_dataset: EvaluationDatasetProvenance
    grader: GraderProvenance
    trials_per_query: int = Field(default=3, ge=1, le=100)
    schedule_seed: int = 17
    comparison: ComparisonConfig = Field(
        default_factory=lambda: ComparisonConfig(
            minimum_trials_per_case=3,
            pass_rate_threshold=2 / 3,
        )
    )
    cache_policy: CachePolicy = CachePolicy.SYSTEM_ISOLATED
    warmup_policy: WarmupPolicy = WarmupPolicy.IDENTICAL_PER_SYSTEM
    accepted_review_statuses: tuple[ReviewStatus, ...] = (
        ReviewStatus.AUTO_VALIDATED,
        ReviewStatus.HUMAN_REVIEWED,
    )

    @model_validator(mode="after")
    def validate_controls_and_contrasts(self) -> ControlledExperimentPlan:
        systems = {item.system_version: item for item in self.systems}
        if len(systems) != len(self.systems):
            raise ValueError("system_version values must be unique")
        if not self.accepted_review_statuses:
            raise ValueError("at least one accepted review status is required")
        if len(self.accepted_review_statuses) != len(set(self.accepted_review_statuses)):
            raise ValueError("accepted_review_statuses must be unique")
        for field in ("corpus", "model", "prompt"):
            values = {getattr(system.versions, field) for system in self.systems}
            if len(values) != 1:
                raise ValueError(f"controlled field differs across systems: {field}")
        if self.comparison.minimum_trials_per_case != self.trials_per_query:
            raise ValueError(
                "comparison.minimum_trials_per_case must equal trials_per_query"
            )
        contrast_ids = [item.contrast_id for item in self.contrasts]
        if len(contrast_ids) != len(set(contrast_ids)):
            raise ValueError("contrast_id values must be unique")
        for contrast in self.contrasts:
            unknown = {
                contrast.baseline_system_version,
                contrast.candidate_system_version,
            } - systems.keys()
            if unknown:
                raise ValueError(f"contrast references unknown systems: {sorted(unknown)}")
            actual = _changed_fields(
                systems[contrast.baseline_system_version],
                systems[contrast.candidate_system_version],
            )
            if set(contrast.intervention_fields) != actual:
                raise ValueError(
                    f"{contrast.contrast_id}: declared intervention fields "
                    f"{sorted(contrast.intervention_fields)} != actual {sorted(actual)}"
                )
        return self


class ExecutionQuery(BaseModel):
    """Gold-redacted input visible to the system under test."""

    model_config = ConfigDict(frozen=True)

    text: str
    language: str
    known_gold_evidence_refs: tuple[str, ...] = ()


class TrialObservation(BaseModel):
    """Raw system output with no quality judgment."""

    model_config = ConfigDict(frozen=True)

    final_answer: str
    retrieved_evidence_refs: tuple[str, ...] = ()
    tool_trace: tuple[ToolCallTrace, ...] = ()
    tool_trace_complete: bool = False
    efficiency: EfficiencyObservation
    effective_seed: int | None = Field(default=None, ge=0)
    provider_request_id: str | None = None


class TrialGrade(BaseModel):
    model_config = ConfigDict(frozen=True)

    outcome: OutcomeScores
    retrieval: RetrievalDiagnostics = Field(default_factory=RetrievalDiagnostics)
    effective_seed: int | None = Field(default=None, ge=0)
    grader_request_id: str | None = None


class ScheduledTrial(BaseModel):
    model_config = ConfigDict(frozen=True)

    system_version: str
    query_id: str
    trial_id: str
    requested_seed: int = Field(ge=0)


class ControlledExperimentBundle(BaseModel):
    model_config = ConfigDict(frozen=True)

    plan: ControlledExperimentPlan
    query_ids: tuple[str, ...] = Field(min_length=1)
    specification_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_order: tuple[ScheduledTrial, ...]
    trials: tuple[TrialRunResult, ...]
    queries: tuple[QueryRecord, ...]
    specifications: tuple[EvalSpecification, ...]

    @model_validator(mode="after")
    def validate_schedule_pairing(self) -> ControlledExperimentBundle:
        if self.query_ids != tuple(sorted(set(self.query_ids))):
            raise ValueError("query_ids must be unique and sorted")
        if tuple(sorted(item.query_id for item in self.queries)) != self.query_ids:
            raise ValueError("query snapshot does not match query_ids")
        if tuple(sorted(item.query_id for item in self.specifications)) != self.query_ids:
            raise ValueError("specification snapshot does not match query_ids")
        if self.specification_fingerprint != _specification_fingerprint(
            self.queries, self.specifications
        ):
            raise ValueError("specification fingerprint does not match input snapshots")
        expected_order = _schedule(self.plan, self.query_ids)
        if self.execution_order != expected_order:
            raise ValueError("execution schedule does not match the declared plan")
        scheduled = tuple(
            (
                item.system_version,
                item.query_id,
                item.trial_id,
                item.requested_seed,
            )
            for item in self.execution_order
        )
        actual = tuple(
            (
                item.system_version,
                item.query_id,
                item.trial_id,
                item.requested_seed,
            )
            for item in self.trials
        )
        if actual != scheduled:
            raise ValueError("trial results do not exactly match the execution schedule")
        systems = {item.system_version: item for item in self.plan.systems}
        specifications = {item.query_id: item for item in self.specifications}
        for trial in self.trials:
            expected_system = systems[trial.system_version]
            expected_specification = specifications[trial.query_id]
            if trial.run_id != self.plan.run_id:
                raise ValueError("trial run_id does not match the declared plan")
            if trial.versions != expected_system.versions:
                raise ValueError("trial versions do not match the declared system")
            if trial.condition != expected_system.condition:
                raise ValueError("trial condition does not match the declared system")
            if (trial.spec_id, trial.spec_version) != (
                expected_specification.spec_id,
                expected_specification.spec_version,
            ):
                raise ValueError("trial specification does not match the input snapshot")
            grader_was_invoked = (
                trial.status == TrialStatus.COMPLETED
                or trial.failure_stage == TrialFailureStage.GRADING
            )
            expected_grader_seed = (
                _grader_trial_seed(
                    self.plan.grader.seed,
                    trial.query_id,
                    trial.trial_id,
                )
                if grader_was_invoked
                else None
            )
            if trial.requested_grader_seed != expected_grader_seed:
                raise ValueError("trial grader seed does not match the declared plan")
        return self


class ControlledComparisonReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    contrast: ArchitectureContrast
    comparison: ComparisonConfig
    grader: GraderProvenance
    summary: PairedComparisonSummary


class TrialExecutor(Protocol):
    def execute(
        self,
        *,
        query: ExecutionQuery,
        system: SystemConfiguration,
        trial_id: str,
        requested_seed: int,
        cache_policy: CachePolicy,
        warmup_policy: WarmupPolicy,
    ) -> TrialObservation: ...


class TrialGrader(Protocol):
    def grade(
        self,
        *,
        query: QueryRecord,
        specification: EvalSpecification,
        observation: TrialObservation,
        provenance: GraderProvenance,
        requested_seed: int | None,
    ) -> TrialGrade: ...


def run_controlled_experiment(
    plan: ControlledExperimentPlan,
    queries: Sequence[QueryRecord],
    specifications: Sequence[EvalSpecification],
    *,
    executor: TrialExecutor,
    grader: TrialGrader,
) -> ControlledExperimentBundle:
    query_by_id = _unique_queries(queries)
    spec_by_query = _specifications_by_query(specifications)
    if set(query_by_id) != set(spec_by_query):
        raise ValueError(
            "query/specification sets differ: "
            f"missing_specs={sorted(set(query_by_id) - set(spec_by_query))}, "
            f"missing_queries={sorted(set(spec_by_query) - set(query_by_id))}"
        )
    rejected = sorted(
        spec.query_id
        for spec in specifications
        if spec.review_status not in plan.accepted_review_statuses
    )
    if rejected:
        raise ValueError(f"specifications have unaccepted review status: {rejected}")
    spec_rubric_versions = {
        spec.grader_rubric_version
        for spec in specifications
        if spec.grader_rubric_version is not None
    }
    undeclared_rubrics = spec_rubric_versions - set(
        plan.grader.compatible_spec_rubric_versions
    )
    if undeclared_rubrics:
        raise ValueError(
            "grader is not declared compatible with spec rubrics: "
            f"{sorted(undeclared_rubrics)}"
        )
    requires_llm_judge = any(
        fact.grader == GraderKind.LLM_JUDGE
        for spec in specifications
        for fact in spec.required_facts
    )
    if requires_llm_judge and (not plan.grader.model or not plan.grader.prompt_version):
        raise ValueError("LLM-graded facts require grader model and prompt provenance")

    query_ids = tuple(sorted(query_by_id))
    systems = {item.system_version: item for item in plan.systems}
    execution_order = _schedule(plan, query_ids)
    trials = []
    for scheduled in execution_order:
        query = query_by_id[scheduled.query_id]
        spec = spec_by_query[scheduled.query_id]
        system = systems[scheduled.system_version]
        execution_query = ExecutionQuery(
            text=query.text,
            language=query.language,
            known_gold_evidence_refs=_known_gold_refs(system.condition, spec),
        )
        started_at = datetime.now(UTC)
        started = time.perf_counter()
        try:
            observation = executor.execute(
                query=execution_query,
                system=system,
                trial_id=scheduled.trial_id,
                requested_seed=scheduled.requested_seed,
                cache_policy=plan.cache_policy,
                warmup_policy=plan.warmup_policy,
            )
        except SystemTimeoutError as error:
            trials.append(
                _failed_trial(
                    plan, system, spec, scheduled, TrialStatus.TIMED_OUT,
                    error, started_at, started, TrialFailureStage.EXECUTION,
                )
            )
            continue
        except SystemExecutionError as error:
            trials.append(
                _failed_trial(
                    plan, system, spec, scheduled, TrialStatus.SYSTEM_FAILED,
                    error, started_at, started, TrialFailureStage.EXECUTION,
                )
            )
            continue
        except Exception as error:  # noqa: BLE001 - preserve harness failures
            trials.append(
                _failed_trial(
                    plan, system, spec, scheduled, TrialStatus.HARNESS_FAILED,
                    error, started_at, started, TrialFailureStage.HARNESS,
                )
            )
            continue
        try:
            grader_seed = _grader_trial_seed(
                plan.grader.seed,
                query.query_id,
                scheduled.trial_id,
            )
            grade = grader.grade(
                query=query,
                specification=spec,
                observation=observation,
                provenance=plan.grader,
                requested_seed=grader_seed,
            )
        except Exception as error:  # noqa: BLE001 - preserve grader failures
            trials.append(
                _failed_trial(
                    plan, system, spec, scheduled, TrialStatus.HARNESS_FAILED,
                    error,
                    started_at,
                    started,
                    TrialFailureStage.GRADING,
                    observation=observation,
                    requested_grader_seed=grader_seed,
                )
            )
            continue
        trials.append(
            TrialRunResult(
                run_id=plan.run_id,
                system_version=system.system_version,
                query_id=query.query_id,
                spec_id=spec.spec_id,
                spec_version=spec.spec_version,
                trial_id=scheduled.trial_id,
                status=TrialStatus.COMPLETED,
                requested_seed=scheduled.requested_seed,
                effective_seed=observation.effective_seed,
                requested_grader_seed=grader_seed,
                effective_grader_seed=grade.effective_seed,
                grader_request_id=grade.grader_request_id,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                provider_request_id=observation.provider_request_id,
                versions=system.versions,
                condition=system.condition,
                retrieved_evidence_refs=observation.retrieved_evidence_refs,
                final_answer=observation.final_answer,
                outcome=grade.outcome,
                retrieval=grade.retrieval,
                tool_trace=observation.tool_trace,
                tool_trace_complete=observation.tool_trace_complete,
                efficiency=observation.efficiency,
            )
        )
    return ControlledExperimentBundle(
        plan=plan,
        query_ids=query_ids,
        specification_fingerprint=_specification_fingerprint(queries, specifications),
        execution_order=execution_order,
        trials=tuple(trials),
        queries=tuple(sorted(queries, key=lambda item: item.query_id)),
        specifications=tuple(
            sorted(specifications, key=lambda item: item.query_id)
        ),
    )


def compare_bundle(
    bundle: ControlledExperimentBundle,
) -> dict[str, ControlledComparisonReport]:
    harness_failures = [
        trial for trial in bundle.trials if trial.status == TrialStatus.HARNESS_FAILED
    ]
    if harness_failures:
        raise ValueError(
            f"cannot compare a run with {len(harness_failures)} harness/grader failures"
        )
    by_system = {
        system.system_version: tuple(
            trial
            for trial in bundle.trials
            if trial.system_version == system.system_version
        )
        for system in bundle.plan.systems
    }
    return {
        contrast.contrast_id: ControlledComparisonReport(
            contrast=contrast,
            comparison=bundle.plan.comparison,
            grader=bundle.plan.grader,
            summary=compare_systems(
                by_system[contrast.baseline_system_version],
                by_system[contrast.candidate_system_version],
                config=bundle.plan.comparison,
                resampling_clusters=_leakage_clusters(bundle.queries),
            ),
        )
        for contrast in bundle.plan.contrasts
    }


def write_controlled_bundle(
    output_root: Path,
    bundle: ControlledExperimentBundle,
) -> Path:
    harness_failure_count = sum(
        trial.status == TrialStatus.HARNESS_FAILED for trial in bundle.trials
    )
    if harness_failure_count:
        reports: dict[str, ControlledComparisonReport] = {}
        comparison_status = {
            "status": "blocked",
            "reason": "harness_or_grader_failures_present",
            "harness_failure_count": harness_failure_count,
        }
    else:
        reports = compare_bundle(bundle)
        comparison_status = {
            "status": "completed",
            "contrast_ids": sorted(reports),
        }
    output_root.mkdir(parents=True, exist_ok=True)
    run_root = output_root / bundle.plan.run_id
    if run_root.exists():
        raise FileExistsError(f"run output already exists: {run_root}")
    partial_root = Path(
        tempfile.mkdtemp(prefix=f".{bundle.plan.run_id}.partial-", dir=output_root)
    )
    try:
        _write_json(partial_root / "manifest.json", bundle.plan.model_dump(mode="json"))
        _write_json(
            partial_root / "schedule.json",
            {
                "specification_fingerprint": bundle.specification_fingerprint,
                "query_ids": bundle.query_ids,
                "execution_order": [
                    item.model_dump(mode="json") for item in bundle.execution_order
                ],
            },
        )
        _write_json(partial_root / "comparison-status.json", comparison_status)
        inputs_root = partial_root / "inputs"
        inputs_root.mkdir()
        _write_jsonl(inputs_root / "queries.jsonl", bundle.queries)
        _write_jsonl(
            inputs_root / "eval-specifications.jsonl", bundle.specifications
        )
        for system in bundle.plan.systems:
            system_trials = sorted(
                (
                    trial
                    for trial in bundle.trials
                    if trial.system_version == system.system_version
                ),
                key=lambda item: (item.query_id, item.trial_id),
            )
            _write_jsonl(
                partial_root / f"{system.system_version}.jsonl", system_trials
            )
        for contrast_id, report in reports.items():
            _write_json(
                partial_root / f"{contrast_id}.json", report.model_dump(mode="json")
            )
        partial_root.rename(run_root)
    except Exception:
        if partial_root.exists():
            failed_root = partial_root.with_name(
                partial_root.name.replace(".partial-", ".failed-", 1)
            )
            partial_root.rename(failed_root)
        raise
    return run_root


def _failed_trial(
    plan: ControlledExperimentPlan,
    system: SystemConfiguration,
    spec: EvalSpecification,
    scheduled: ScheduledTrial,
    status: TrialStatus,
    error: Exception,
    started_at: datetime,
    started: float,
    failure_stage: TrialFailureStage,
    observation: TrialObservation | None = None,
    requested_grader_seed: int | None = None,
) -> TrialRunResult:
    return TrialRunResult(
        run_id=plan.run_id,
        system_version=system.system_version,
        query_id=spec.query_id,
        spec_id=spec.spec_id,
        spec_version=spec.spec_version,
        trial_id=scheduled.trial_id,
        status=status,
        requested_seed=scheduled.requested_seed,
        requested_grader_seed=requested_grader_seed,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        versions=system.versions,
        condition=system.condition,
        effective_seed=observation.effective_seed if observation else None,
        provider_request_id=observation.provider_request_id if observation else None,
        retrieved_evidence_refs=(
            observation.retrieved_evidence_refs if observation else ()
        ),
        final_answer=observation.final_answer if observation else "",
        outcome=OutcomeScores(
            task_success=False,
            required_fact_coverage=0.0,
            behavior_correct=False,
        ),
        tool_trace=observation.tool_trace if observation else (),
        tool_trace_complete=observation.tool_trace_complete if observation else False,
        efficiency=(
            observation.efficiency
            if observation
            else EfficiencyObservation(
                end_to_end_latency_ms=(time.perf_counter() - started) * 1000,
                telemetry_complete=False,
                measurement_notes="trial did not complete",
            )
        ),
        error_type=type(error).__name__,
        error_message=_safe_error_message(error),
        failure_stage=failure_stage,
    )


def _schedule(
    plan: ControlledExperimentPlan, query_ids: Sequence[str]
) -> tuple[ScheduledTrial, ...]:
    rng = random.Random(plan.schedule_seed)
    blocks = [
        (query_id, f"trial-{trial_number:03d}")
        for query_id in query_ids
        for trial_number in range(1, plan.trials_per_query + 1)
    ]
    rng.shuffle(blocks)
    scheduled = []
    for query_id, trial_id in blocks:
        systems = list(plan.systems)
        rng.shuffle(systems)
        requested_seed = _paired_trial_seed(plan.schedule_seed, query_id, trial_id)
        scheduled.extend(
            ScheduledTrial(
                system_version=system.system_version,
                query_id=query_id,
                trial_id=trial_id,
                requested_seed=requested_seed,
            )
            for system in systems
        )
    return tuple(scheduled)


def _known_gold_refs(
    condition: ExperimentCondition, specification: EvalSpecification
) -> tuple[str, ...]:
    if not condition.known_gold_evidence_injected:
        return ()
    return tuple(
        sorted(
            item.evidence_ref
            for item in specification.evidence_assessments
            if item.judgment == EvidenceJudgment.KNOWN_RELEVANT
        )
    )


def _changed_fields(
    baseline: SystemConfiguration, candidate: SystemConfiguration
) -> set[str]:
    fields = {
        field
        for field in ("index", "toolset", "code_commit")
        if getattr(baseline.versions, field) != getattr(candidate.versions, field)
    }
    if baseline.condition != candidate.condition:
        fields.add("condition")
    return fields


def _paired_trial_seed(schedule_seed: int, query_id: str, trial_id: str) -> int:
    payload = f"{schedule_seed}:{query_id}:{trial_id}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big")


def _grader_trial_seed(
    base_seed: int | None, query_id: str, trial_id: str
) -> int | None:
    if base_seed is None:
        return None
    return _paired_trial_seed(base_seed, query_id, trial_id)


def _leakage_clusters(queries: Sequence[QueryRecord]) -> dict[str, str]:
    parent = {query.query_id: query.query_id for query in queries}

    def find(query_id: str) -> str:
        while parent[query_id] != query_id:
            parent[query_id] = parent[parent[query_id]]
            query_id = parent[query_id]
        return query_id

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    owner_by_group: dict[str, str] = {}
    for query in queries:
        for group_id in query.leakage_group_ids:
            owner = owner_by_group.setdefault(group_id, query.query_id)
            union(query.query_id, owner)
    return {query.query_id: find(query.query_id) for query in queries}


def _safe_error_message(error: Exception) -> str:
    return " ".join(str(error).split())[:1000]


def _unique_queries(queries: Sequence[QueryRecord]) -> dict[str, QueryRecord]:
    output: dict[str, QueryRecord] = {}
    for query in queries:
        if query.query_id in output:
            raise ValueError(f"duplicate query id: {query.query_id}")
        output[query.query_id] = query
    if not output:
        raise ValueError("query set is empty")
    return output


def _specifications_by_query(
    specifications: Sequence[EvalSpecification],
) -> dict[str, EvalSpecification]:
    output: dict[str, EvalSpecification] = {}
    for spec in specifications:
        if spec.query_id in output:
            raise ValueError(f"multiple specifications for query: {spec.query_id}")
        output[spec.query_id] = spec
    return output


def _specification_fingerprint(
    queries: Sequence[QueryRecord], specifications: Sequence[EvalSpecification]
) -> str:
    payload = {
        "queries": [
            item.model_dump(mode="json")
            for item in sorted(queries, key=lambda item: item.query_id)
        ],
        "specifications": [
            item.model_dump(mode="json")
            for item in sorted(specifications, key=lambda item: item.query_id)
        ],
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, items: Sequence[BaseModel]) -> None:
    path.write_text(
        "".join(
            json.dumps(
                trial.model_dump(mode="json"), ensure_ascii=False, sort_keys=True
            )
            + "\n"
            for trial in items
        ),
        encoding="utf-8",
    )
