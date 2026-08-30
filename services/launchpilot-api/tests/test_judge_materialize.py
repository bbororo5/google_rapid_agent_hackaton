from __future__ import annotations

from pathlib import Path

from launchpilot.evaluation.contracts import GraderKind, ReviewStatus
from launchpilot.evaluation.judging.contracts import (
    JudgeCall,
    JudgeCallMetadata,
    SpecificationAdjudication,
    SpecificationAdjudicationVerdict,
)
from launchpilot.evaluation.judging.materialize import (
    SpecificationAdjudicationOutcome,
    materialize_judge_ready_dataset,
)
from launchpilot.evaluation.judging.spec_adjudicator import (
    AdjudicationDecision,
    AdjudicationPass,
    SpecificationAdjudicationRecord,
)
from launchpilot.evaluation.task_dataset import load_task_dataset


def test_materializer_creates_new_partial_snapshot_without_mutating_source(
    tmp_path: Path,
) -> None:
    source_root = (
        Path(__file__).parents[1] / "evals" / "datasets" / "marketing-ops-task-v1"
    )
    source_manifest_before = (source_root / "manifest.json").read_bytes()
    source = load_task_dataset(source_root)
    accepted_id = next(
        item.problem_id for item in source.specifications if item.required_facts
    )
    outcomes = tuple(
        SpecificationAdjudicationOutcome(
            problem_id=problem.problem_id,
            decision=(
                AdjudicationDecision.ACCEPTED
                if problem.problem_id == accepted_id
                else AdjudicationDecision.NEEDS_REVIEW
            ),
            reason=(
                "two independent passes accepted"
                if problem.problem_id == accepted_id
                else "not adjudicated"
            ),
            record=_record(problem.problem_id) if problem.problem_id == accepted_id else None,
        )
        for problem in source.problems
    )

    output_root = tmp_path / "marketing-ops-task-2026-08-judge-ready"
    output = materialize_judge_ready_dataset(
        source_root=source_root,
        source=source,
        output_root=output_root,
        outcomes=outcomes,
    )

    assert (source_root / "manifest.json").read_bytes() == source_manifest_before
    assert output.manifest.dataset_version == "2026-08-judge-ready"
    assert output.manifest.release_ready is False
    assert output.manifest.adjudication_status == "partial:1/150_accepted"
    promoted = next(
        item for item in output.specifications if item.problem_id == accepted_id
    )
    assert promoted.review_status == ReviewStatus.MACHINE_ADJUDICATED
    assert all(fact.grader == GraderKind.LLM_JUDGE for fact in promoted.required_facts)
    assert promoted.grader_rubric_version == "task-answer-v1"
    assert all(
        artifact.path.startswith("world/artifacts/")
        for artifact in output.world.artifacts
    )
    assert len(
        (
            output_root / "adjudication" / "machine-adjudications.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ) == 150


def _record(problem_id: str) -> SpecificationAdjudicationRecord:
    verdict = SpecificationAdjudication(
        verdict=SpecificationAdjudicationVerdict.ACCEPT,
        problem_spec_aligned=True,
        required_facts_supported=True,
        answerability_consistent=True,
        behavior_consistent=True,
        tool_independent=True,
        rationale="모든 검사를 통과했다.",
    )
    passes = tuple(
        AdjudicationPass(
            pass_number=number,
            call=JudgeCall[SpecificationAdjudication](
                payload=verdict,
                metadata=JudgeCallMetadata(
                    model="gemini-3.7-flash",
                    thinking_level="medium",
                    latency_ms=1,
                    retry_count=0,
                    response_fingerprint="sha256:" + str(number) * 64,
                    response_status="completed",
                ),
            ),
        )
        for number in (1, 2)
    )
    return SpecificationAdjudicationRecord(
        problem_id=problem_id,
        spec_id=f"{problem_id}.spec",
        source_spec_version="v1-draft",
        source_spec_fingerprint="sha256:" + "a" * 64,
        rubric_version="spec-adjudication-v1",
        response_schema_version="specification-adjudication-v1",
        decision=AdjudicationDecision.ACCEPTED,
        passes=passes,  # type: ignore[arg-type]
        decision_reason="two independent passes accepted",
    )
