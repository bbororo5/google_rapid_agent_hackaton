from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from launchpilot.evaluation.contracts import GraderKind, ReviewStatus
from launchpilot.evaluation.task_dataset import (
    TaskDataset,
    TaskDatasetManifest,
    WorldArtifact,
    WorldManifest,
    load_task_dataset,
)

from .spec_adjudicator import (
    AdjudicationDecision,
    SpecificationAdjudicationRecord,
)


class SpecificationAdjudicationOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    problem_id: str = Field(min_length=1)
    decision: AdjudicationDecision
    reason: str = Field(min_length=1)
    record: SpecificationAdjudicationRecord | None = None

    @model_validator(mode="after")
    def accepted_requires_record(self) -> SpecificationAdjudicationOutcome:
        if self.decision == AdjudicationDecision.ACCEPTED and self.record is None:
            raise ValueError("accepted adjudication outcome requires a two-pass record")
        if self.record is not None and self.record.problem_id != self.problem_id:
            raise ValueError("outcome and adjudication record problem ids differ")
        return self


def materialize_judge_ready_dataset(
    *,
    source_root: Path,
    source: TaskDataset,
    output_root: Path,
    outcomes: Sequence[SpecificationAdjudicationOutcome],
    dataset_version: str = "2026-08-judge-ready",
    spec_version: str = "judge-ready-2026-08",
    answer_rubric_version: str = "task-answer-v1",
) -> TaskDataset:
    """Create a new immutable snapshot; never mutate the frontier source dataset."""

    outcome_by_id = _unique_outcomes(outcomes)
    problem_ids = {problem.problem_id for problem in source.problems}
    if set(outcome_by_id) != problem_ids:
        raise ValueError("adjudication outcomes must cover every source problem")
    if output_root.exists():
        raise FileExistsError(f"output dataset already exists: {output_root}")

    accepted = {
        problem_id
        for problem_id, outcome in outcome_by_id.items()
        if outcome.decision == AdjudicationDecision.ACCEPTED
    }
    specifications = tuple(
        _promote_specification(
            specification,
            spec_version=spec_version,
            answer_rubric_version=answer_rubric_version,
        )
        if specification.problem_id in accepted
        else specification
        for specification in source.specifications
    )
    status = "complete" if len(accepted) == len(source.problems) else "partial"
    manifest = TaskDatasetManifest(
        dataset_id=source.manifest.dataset_id,
        dataset_version=dataset_version,
        lifecycle=source.manifest.lifecycle,
        # Machine agreement is not grader calibration or production approval.
        release_ready=False,
        source_fixture=(
            f"{source.manifest.dataset_id}:{source.manifest.dataset_version}"
        ),
        world_id=source.world.world_id,
        problem_count=len(source.problems),
        specification_count=len(specifications),
        evidence_judgment_count=len(source.evidence_judgments),
        reference_answer_count=len(source.reference_answers),
        adjudication_status=(
            f"{status}:{len(accepted)}/{len(source.problems)}_accepted"
        ),
        adjudication_policy="spec-adjudication-v1+two-pass-consensus-v1",
        source_dataset_fingerprint="sha256:" + source.fingerprint,
        prohibited_uses=tuple(
            dict.fromkeys(
                (
                    *source.manifest.prohibited_uses,
                    "using_needs_review_specs_for_release_decisions",
                )
            )
        ),
    )

    output_root.parent.mkdir(parents=True, exist_ok=True)
    partial_root = Path(
        tempfile.mkdtemp(prefix=f".{output_root.name}.partial-", dir=output_root.parent)
    )
    try:
        world = _copy_world(source_root, partial_root, source)
        _write_json(partial_root / "manifest.json", manifest.model_dump(mode="json"))
        _write_json(
            partial_root / "world" / "manifest.json", world.model_dump(mode="json")
        )
        _write_jsonl(partial_root / "problems" / "problems.jsonl", source.problems)
        _write_jsonl(
            partial_root / "specifications" / "eval-specifications.jsonl",
            specifications,
            exclude={"evidence_assessments"},
        )
        _write_jsonl(
            partial_root / "judgments" / "evidence-assessments.jsonl",
            source.evidence_judgments,
        )
        if source.reference_answers:
            _write_jsonl(
                partial_root / "references" / "answer-examples.jsonl",
                source.reference_answers,
            )
        _write_jsonl(
            partial_root / "adjudication" / "machine-adjudications.jsonl",
            tuple(outcome_by_id[problem_id] for problem_id in sorted(problem_ids)),
        )
        partial_root.rename(output_root)
    except Exception:
        failed_root = partial_root.with_name(
            partial_root.name.replace(".partial-", ".failed-", 1)
        )
        partial_root.rename(failed_root)
        raise
    return load_task_dataset(output_root)


def _promote_specification(
    specification,
    *,
    spec_version: str,
    answer_rubric_version: str,
):
    required_facts = tuple(
        fact.model_copy(update={"grader": GraderKind.LLM_JUDGE})
        if fact.grader == GraderKind.HUMAN
        else fact
        for fact in specification.required_facts
    )
    return specification.model_copy(
        update={
            "spec_version": spec_version,
            "required_facts": required_facts,
            "review_status": ReviewStatus.MACHINE_ADJUDICATED,
            "reviewer_ids": (),
            "grader_rubric_version": answer_rubric_version,
        }
    )


def _copy_world(
    source_root: Path, partial_root: Path, source: TaskDataset
) -> WorldManifest:
    artifacts = []
    for artifact in source.world.artifacts:
        source_path = (source_root / artifact.path).resolve()
        suffix = source_path.suffix or ".jsonl"
        relative = Path("world") / "artifacts" / f"{artifact.role}{suffix}"
        destination = partial_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        artifacts.append(
            WorldArtifact(
                role=artifact.role,
                path=str(relative),
                sha256=artifact.sha256,
                record_count=artifact.record_count,
            )
        )
    return source.world.model_copy(update={"artifacts": tuple(artifacts)})


def _unique_outcomes(
    outcomes: Sequence[SpecificationAdjudicationOutcome],
) -> Mapping[str, SpecificationAdjudicationOutcome]:
    result = {}
    for outcome in outcomes:
        if outcome.problem_id in result:
            raise ValueError(f"duplicate adjudication outcome: {outcome.problem_id}")
        result[outcome.problem_id] = outcome
    return result


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(
    path: Path,
    records: Sequence[BaseModel],
    *,
    exclude: set[str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(
                record.model_dump(mode="json", exclude=exclude),
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
