from __future__ import annotations

import json
from pathlib import Path

import pytest

from launchpilot.evaluation import controlled_runner
from launchpilot.evaluation.contracts import (
    Answerability,
    ArtifactVersions,
    EfficiencyObservation,
    EvalSpecification,
    ExpectedBehavior,
    GraderKind,
    InformationModality,
    OutcomeScores,
    PortfolioRole,
    QueryCharacteristics,
    QueryRecord,
    QuerySource,
    RequiredFact,
    RetrievalDiagnostics,
    ReviewStatus,
    TaskShape,
    TrialStatus,
)
from launchpilot.evaluation.controlled_runner import (
    ArchitectureContrast,
    ControlledExperimentPlan,
    EvaluationDatasetProvenance,
    GraderProvenance,
    SystemConfiguration,
    SystemExecutionError,
    TrialGrade,
    TrialObservation,
    compare_bundle,
    run_controlled_experiment,
    write_controlled_bundle,
)
from launchpilot.evaluation.paired_comparison import ComparisonConfig


class _Executor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, int]] = []
        self.visible_queries = []

    def execute(self, **kwargs) -> TrialObservation:
        query = kwargs["query"]
        system = kwargs["system"]
        trial_id = kwargs["trial_id"]
        seed = kwargs["requested_seed"]
        query_label = query.text.removeprefix("question ")
        self.calls.append((system.system_version, query_label, trial_id, seed))
        self.visible_queries.append(query)
        succeeds = system.system_version != "v0" or query_label == "q1"
        return TrialObservation(
            final_answer="42" if succeeds else "unknown",
            retrieved_evidence_refs=("doc:answer",) if succeeds else (),
            tool_trace_complete=True,
            efficiency=EfficiencyObservation(
                end_to_end_latency_ms={"v0": 20, "v1": 30, "v2": 40}[
                    system.system_version
                ],
                cost_usd={"v0": 0.01, "v1": 0.02, "v2": 0.03}[
                    system.system_version
                ],
                telemetry_complete=True,
            ),
            effective_seed=seed,
            provider_request_id=f"request-{len(self.calls)}",
        )


class _Grader:
    def grade(self, **kwargs) -> TrialGrade:
        observation = kwargs["observation"]
        succeeds = observation.final_answer == "42"
        return TrialGrade(
            outcome=OutcomeScores(
                task_success=succeeds,
                required_fact_coverage=1.0 if succeeds else 0.0,
                groundedness=1.0 if succeeds else 0.0,
                answer_relevance=1.0 if succeeds else 0.0,
                behavior_correct=succeeds,
            ),
            retrieval=RetrievalDiagnostics(
                cutoff_k=5,
                known_relevant_recall_at_k=1.0 if succeeds else 0.0,
                answer_bearing_evidence_retrieved=succeeds,
            ),
            effective_seed=kwargs["requested_seed"],
            grader_request_id=(
                f"grader-{kwargs['requested_seed']}"
                if kwargs["requested_seed"] is not None
                else None
            ),
        )


def test_controlled_runner_redacts_gold_pairs_blocks_and_writes_reports(
    tmp_path: Path,
) -> None:
    executor = _Executor()
    bundle = run_controlled_experiment(
        _plan(),
        [_query("q2"), _query("q1")],
        [_spec("q1"), _spec("q2")],
        executor=executor,
        grader=_Grader(),
    )

    assert len(bundle.trials) == 18
    assert bundle.query_ids == ("q1", "q2")
    assert all(not item.known_gold_evidence_refs for item in executor.visible_queries)
    assert all("query_id" not in type(item).model_fields for item in executor.visible_queries)
    assert all(
        "characteristics" not in type(item).model_fields
        for item in executor.visible_queries
    )
    for offset in range(0, len(bundle.execution_order), 3):
        block = bundle.execution_order[offset : offset + 3]
        assert len({(item.query_id, item.trial_id) for item in block}) == 1
        assert len({item.requested_seed for item in block}) == 1
        assert {item.system_version for item in block} == {"v0", "v1", "v2"}
    assert all(trial.requested_seed is not None for trial in bundle.trials)
    assert all(trial.effective_seed == trial.requested_seed for trial in bundle.trials)

    reports = compare_bundle(bundle)
    assert set(reports) == {"v0-v1", "v1-v2"}
    assert reports["v0-v1"].summary.newly_solved == 1
    assert reports["v0-v1"].summary.pass_to_pass == 1
    assert reports["v1-v2"].summary.pass_to_pass == 2
    assert reports["v0-v1"].grader.grader_id == "deterministic-test"
    assert reports[
        "v0-v1"
    ].summary.task_success_rate_delta.independent_cluster_count == 2
    assert (
        reports["v0-v1"].summary.task_success_rate_delta.resampling_unit
        == "leakage_cluster_then_matched_trial_pair"
    )
    assert (
        reports["v0-v1"].summary.answer_bearing_evidence_rate_delta
        == pytest.approx(0.5)
    )
    assert reports["v0-v1"].summary.known_relevant_recall_at_k_delta == (
        pytest.approx(0.5)
    )

    run_root = write_controlled_bundle(tmp_path, bundle)
    manifest = json.loads((run_root / "manifest.json").read_text())
    assert manifest["run_id"] == "paired-test"
    assert manifest["comparison"]["pass_rate_threshold"] == pytest.approx(2 / 3)
    assert manifest["cache_policy"] == "system_isolated"
    assert len((run_root / "v0.jsonl").read_text().splitlines()) == 6
    assert (run_root / "v0-v1.json").exists()
    assert (run_root / "v1-v2.json").exists()
    assert len((run_root / "inputs/queries.jsonl").read_text().splitlines()) == 2
    assert len(
        (run_root / "inputs/eval-specifications.jsonl").read_text().splitlines()
    ) == 2
    assert json.loads((run_root / "comparison-status.json").read_text())[
        "status"
    ] == "completed"
    with pytest.raises(FileExistsError):
        write_controlled_bundle(tmp_path, bundle)


def test_plan_rejects_uncontrolled_or_misdeclared_changes() -> None:
    systems = list(_systems())
    systems[1] = systems[1].model_copy(
        update={
            "versions": systems[1].versions.model_copy(update={"model": "other-model"})
        }
    )
    with pytest.raises(ValueError, match="controlled field differs.*model"):
        _plan(systems=tuple(systems))

    bad_contrast = _contrasts()[0].model_copy(update={"intervention_fields": ("index",)})
    with pytest.raises(ValueError, match="declared intervention fields"):
        _plan(contrasts=(bad_contrast, _contrasts()[1]))


def test_runner_rejects_missing_specs_and_unreviewed_specs() -> None:
    with pytest.raises(ValueError, match="query/specification sets differ"):
        run_controlled_experiment(
            _plan(),
            [_query("q1"), _query("q2")],
            [_spec("q1")],
            executor=_Executor(),
            grader=_Grader(),
        )

    unreviewed = _spec("q1").model_copy(
        update={"review_status": ReviewStatus.NEEDS_REVIEW}
    )
    with pytest.raises(ValueError, match="unaccepted review status"):
        run_controlled_experiment(
            _plan(),
            [_query("q1")],
            [unreviewed],
            executor=_Executor(),
            grader=_Grader(),
        )


def test_system_failures_are_counted_but_harness_failures_block_comparison(
    tmp_path: Path,
) -> None:
    class FailingExecutor(_Executor):
        def execute(self, **kwargs) -> TrialObservation:
            if kwargs["system"].system_version == "v0":
                raise SystemExecutionError("provider unavailable")
            return super().execute(**kwargs)

    failed = run_controlled_experiment(
        _plan(),
        [_query("q1")],
        [_spec("q1")],
        executor=FailingExecutor(),
        grader=_Grader(),
    )
    v0_trials = [item for item in failed.trials if item.system_version == "v0"]
    assert all(item.status == TrialStatus.SYSTEM_FAILED for item in v0_trials)
    assert all(not item.outcome.task_success for item in v0_trials)
    assert compare_bundle(failed)["v0-v1"].summary.newly_solved == 1

    class BrokenGrader:
        def grade(self, **kwargs) -> TrialGrade:
            raise RuntimeError("bad rubric")

    broken = run_controlled_experiment(
        _plan(),
        [_query("q1")],
        [_spec("q1")],
        executor=_Executor(),
        grader=BrokenGrader(),
    )
    assert all(item.status == TrialStatus.HARNESS_FAILED for item in broken.trials)
    assert all(item.final_answer == "42" for item in broken.trials)
    assert all(item.failure_stage.value == "grading" for item in broken.trials)
    with pytest.raises(ValueError, match="harness/grader failures"):
        compare_bundle(broken)
    blocked_root = write_controlled_bundle(tmp_path / "blocked", broken)
    comparison_status = json.loads(
        (blocked_root / "comparison-status.json").read_text()
    )
    assert comparison_status == {
        "harness_failure_count": 9,
        "reason": "harness_or_grader_failures_present",
        "status": "blocked",
    }
    assert not (blocked_root / "v0-v1.json").exists()


def test_schedule_and_fingerprint_are_deterministic() -> None:
    kwargs = {
        "plan": _plan(),
        "queries": [_query("q1")],
        "specifications": [_spec("q1")],
        "executor": _Executor(),
        "grader": _Grader(),
    }
    left = run_controlled_experiment(**kwargs)
    right = run_controlled_experiment(**kwargs)

    assert left.execution_order == right.execution_order
    assert left.specification_fingerprint == right.specification_fingerprint

    tampered = left.model_dump(mode="json")
    tampered["trials"].append(tampered["trials"][0])
    with pytest.raises(ValueError, match="trial results do not exactly match"):
        type(left).model_validate(tampered)

    wrong_versions = left.model_dump(mode="json")
    wrong_versions["trials"][0]["versions"]["index"] = "undeclared-index"
    with pytest.raises(ValueError, match="versions do not match"):
        type(left).model_validate(wrong_versions)

    wrong_spec = left.model_dump(mode="json")
    wrong_spec["trials"][0]["spec_version"] = "undeclared-spec"
    with pytest.raises(ValueError, match="specification does not match"):
        type(left).model_validate(wrong_spec)


def test_failed_artifact_publish_is_auditable_and_retryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = run_controlled_experiment(
        _plan(),
        [_query("q1")],
        [_spec("q1")],
        executor=_Executor(),
        grader=_Grader(),
    )
    original = controlled_runner._write_json

    def fail_on_schedule(path: Path, payload: object) -> None:
        if path.name == "schedule.json":
            raise OSError("simulated disk failure")
        original(path, payload)

    monkeypatch.setattr(controlled_runner, "_write_json", fail_on_schedule)
    with pytest.raises(OSError, match="simulated disk failure"):
        write_controlled_bundle(tmp_path, bundle)
    assert not (tmp_path / "paired-test").exists()
    assert not tuple(tmp_path.glob(".paired-test.partial-*"))
    assert len(tuple(tmp_path.glob(".paired-test.failed-*"))) == 1

    monkeypatch.setattr(controlled_runner, "_write_json", original)
    assert write_controlled_bundle(tmp_path, bundle).exists()


def test_llm_grader_provenance_and_trial_seed_are_enforced() -> None:
    payload = _spec("q1").model_dump(mode="json")
    payload["required_facts"][0]["grader"] = "llm_judge"
    payload["grader_rubric_version"] = "judge-rubric-v1"
    llm_spec = EvalSpecification.model_validate(payload)
    compatible = _plan().grader.model_copy(
        update={"compatible_spec_rubric_versions": ("judge-rubric-v1",)}
    )
    incomplete_plan = _plan().model_copy(update={"grader": compatible})

    with pytest.raises(ValueError, match="require grader model and prompt"):
        run_controlled_experiment(
            incomplete_plan,
            [_query("q1")],
            [llm_spec],
            executor=_Executor(),
            grader=_Grader(),
        )

    llm_grader = compatible.model_copy(
        update={"model": "judge-model-v1", "prompt_version": "judge-prompt-v1", "seed": 29}
    )
    bundle = run_controlled_experiment(
        _plan().model_copy(update={"grader": llm_grader}),
        [_query("q1")],
        [llm_spec],
        executor=_Executor(),
        grader=_Grader(),
    )
    assert all(item.requested_grader_seed is not None for item in bundle.trials)
    assert all(
        item.effective_grader_seed == item.requested_grader_seed
        for item in bundle.trials
    )
    assert all(item.grader_request_id for item in bundle.trials)


def test_leakage_groups_are_the_top_level_bootstrap_unit() -> None:
    bundle = run_controlled_experiment(
        _plan(),
        [_query("q1", leakage_group_ids=("template:shared",)), _query("q2", leakage_group_ids=("template:shared",))],
        [_spec("q1"), _spec("q2")],
        executor=_Executor(),
        grader=_Grader(),
    )

    interval = compare_bundle(bundle)["v0-v1"].summary.task_success_rate_delta
    assert interval.independent_cluster_count == 1


def _plan(
    *,
    systems: tuple[SystemConfiguration, ...] | None = None,
    contrasts: tuple[ArchitectureContrast, ...] | None = None,
) -> ControlledExperimentPlan:
    return ControlledExperimentPlan(
        run_id="paired-test",
        systems=systems or _systems(),
        contrasts=contrasts or _contrasts(),
        evaluation_dataset=EvaluationDatasetProvenance(
            dataset_id="paired-fixture",
            dataset_version="v1",
            artifact_uri="memory://paired-fixture-v1",
            source_artifact_fingerprint="sha256:" + "a" * 64,
            selection_id="all-fixture-cases",
        ),
        grader=GraderProvenance(
            grader_id="deterministic-test",
            code_commit="grader123",
            rubric_version="rubric-v1",
            calibration_version="human-calibration-v1",
        ),
        trials_per_query=3,
        schedule_seed=11,
        comparison=ComparisonConfig(
            minimum_trials_per_case=3,
            pass_rate_threshold=2 / 3,
            bootstrap_samples=100,
        ),
    )


def _systems() -> tuple[SystemConfiguration, ...]:
    controls = {
        "corpus": "frozen-v0",
        "model": "model-v1",
        "prompt": "prompt-v1",
        "code_commit": "abc123",
    }
    return (
        SystemConfiguration(
            system_version="v0",
            versions=ArtifactVersions(
                **controls, index="bm25-v1", toolset="sql-bm25-v1"
            ),
        ),
        SystemConfiguration(
            system_version="v1",
            versions=ArtifactVersions(
                **controls,
                index="bm25-dense-v1",
                toolset="sql-bm25-dense-v1",
            ),
        ),
        SystemConfiguration(
            system_version="v2",
            versions=ArtifactVersions(
                **controls,
                index="bm25-dense-graph-v1",
                toolset="sql-bm25-dense-graph-v1",
            ),
        ),
    )


def _contrasts() -> tuple[ArchitectureContrast, ...]:
    return (
        ArchitectureContrast(
            contrast_id="v0-v1",
            baseline_system_version="v0",
            candidate_system_version="v1",
            hypothesis="Dense retrieval improves task success over SQL plus BM25.",
            intervention_fields=("index", "toolset"),
        ),
        ArchitectureContrast(
            contrast_id="v1-v2",
            baseline_system_version="v1",
            candidate_system_version="v2",
            hypothesis="Graph retrieval adds marginal capability over Dense.",
            intervention_fields=("index", "toolset"),
        ),
    )


def _query(
    query_id: str, *, leakage_group_ids: tuple[str, ...] = ()
) -> QueryRecord:
    return QueryRecord(
        query_id=query_id,
        text=f"question {query_id}",
        source=QuerySource.SYNTHETIC,
        portfolio=PortfolioRole.FROZEN,
        characteristics=QueryCharacteristics(
            modalities=(InformationModality.STRUCTURED,),
            task_shape=TaskShape.LOOKUP,
        ),
        leakage_group_ids=leakage_group_ids,
    )


def _spec(query_id: str) -> EvalSpecification:
    return EvalSpecification(
        spec_id=f"{query_id}.spec",
        spec_version="v1",
        query_id=query_id,
        answerability=Answerability.ANSWERABLE,
        expected_behaviors=(ExpectedBehavior.ANSWER,),
        required_facts=(
            RequiredFact(
                fact_id="answer",
                description="expected answer",
                grader=GraderKind.DETERMINISTIC,
                expected_values=("42",),
            ),
        ),
        review_status=ReviewStatus.AUTO_VALIDATED,
    )
