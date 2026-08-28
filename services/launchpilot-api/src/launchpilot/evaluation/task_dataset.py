from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from launchpilot.evaluation.contracts import (
    EvalSpecification,
    EvidenceAssessment,
    ProblemRecord,
)


class WorldArtifact(BaseModel):
    """A canonical world input, never an index or retrieval implementation."""

    model_config = ConfigDict(frozen=True)

    role: str = Field(min_length=1)
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    record_count: int = Field(ge=0)


class WorldManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    world_id: str = Field(min_length=1)
    world_version: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    description: str = Field(min_length=1)
    artifacts: tuple[WorldArtifact, ...] = Field(min_length=1)
    representation_notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_unique_roles(self) -> WorldManifest:
        roles = [artifact.role for artifact in self.artifacts]
        if len(roles) != len(set(roles)):
            raise ValueError("world artifact roles must be unique")
        return self


class EvidenceJudgmentRecord(BaseModel):
    """A problem-keyed assessment stored separately from its success specification."""

    model_config = ConfigDict(frozen=True)

    problem_id: str = Field(min_length=1)
    assessment: EvidenceAssessment


class ReferenceAnswerRecord(BaseModel):
    """An optional example answer; never the definition of task success."""

    model_config = ConfigDict(frozen=True)

    problem_id: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    status: str = Field(min_length=1)
    grading_authority: bool = False
    provenance: str = Field(min_length=1)


class TaskDatasetManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    lifecycle: str = Field(min_length=1)
    release_ready: bool
    source_fixture: str = Field(min_length=1)
    world_id: str = Field(min_length=1)
    problem_count: int = Field(ge=0)
    specification_count: int = Field(ge=0)
    evidence_judgment_count: int = Field(ge=0)
    reference_answer_count: int = Field(ge=0)
    human_review_status: str = Field(min_length=1)
    prohibited_uses: tuple[str, ...] = ()


class TaskDataset(BaseModel):
    """Validated pre-run artifacts for task-centric architecture experiments."""

    model_config = ConfigDict(frozen=True)

    manifest: TaskDatasetManifest
    world: WorldManifest
    problems: tuple[ProblemRecord, ...]
    specifications: tuple[EvalSpecification, ...]
    evidence_judgments: tuple[EvidenceJudgmentRecord, ...]
    reference_answers: tuple[ReferenceAnswerRecord, ...] = ()

    @model_validator(mode="after")
    def validate_references_and_counts(self) -> TaskDataset:
        problem_by_id = _unique(self.problems, "problem_id", "problem")
        spec_by_problem = _unique(
            self.specifications, "problem_id", "specification"
        )
        if set(problem_by_id) != set(spec_by_problem):
            raise ValueError("problem and specification ids must match exactly")
        if {problem.world_id for problem in self.problems} != {self.world.world_id}:
            raise ValueError("all problems must reference the dataset world")

        unknown_judgments = sorted(
            {
                record.problem_id
                for record in self.evidence_judgments
                if record.problem_id not in problem_by_id
            }
        )
        if unknown_judgments:
            raise ValueError(
                f"evidence judgments reference unknown problems: {unknown_judgments}"
            )
        unknown_references = sorted(
            {
                record.problem_id
                for record in self.reference_answers
                if record.problem_id not in problem_by_id
            }
        )
        if unknown_references:
            raise ValueError(
                f"reference answers reference unknown problems: {unknown_references}"
            )

        judgments_by_problem: dict[str, list[EvidenceAssessment]] = {}
        seen_judgments: set[tuple[str, str]] = set()
        for record in self.evidence_judgments:
            key = (record.problem_id, record.assessment.evidence_ref)
            if key in seen_judgments:
                raise ValueError(
                    "duplicate evidence judgment: "
                    f"{record.problem_id}/{record.assessment.evidence_ref}"
                )
            seen_judgments.add(key)
            judgments_by_problem.setdefault(record.problem_id, []).append(
                record.assessment
            )

        for specification in self.specifications:
            expected = tuple(
                sorted(
                    judgments_by_problem.get(specification.problem_id, ()),
                    key=lambda item: item.evidence_ref,
                )
            )
            if specification.evidence_assessments != expected:
                raise ValueError(
                    "specification evidence assessments must be hydrated from the "
                    f"judgment artifact: {specification.problem_id}"
                )

        counts = {
            "problem_count": len(self.problems),
            "specification_count": len(self.specifications),
            "evidence_judgment_count": len(self.evidence_judgments),
            "reference_answer_count": len(self.reference_answers),
        }
        for field, actual in counts.items():
            if getattr(self.manifest, field) != actual:
                raise ValueError(
                    f"manifest {field}={getattr(self.manifest, field)} != {actual}"
                )
        if self.manifest.world_id != self.world.world_id:
            raise ValueError("dataset manifest and world manifest disagree")
        return self

    @property
    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json")
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


def load_task_dataset(root: Path) -> TaskDataset:
    manifest = TaskDatasetManifest.model_validate_json(
        (root / "manifest.json").read_text(encoding="utf-8")
    )
    world = WorldManifest.model_validate_json(
        (root / "world" / "manifest.json").read_text(encoding="utf-8")
    )
    problems = tuple(
        ProblemRecord.model_validate(item)
        for item in _jsonl(root / "problems" / "problems.jsonl")
    )
    raw_specs = tuple(
        EvalSpecification.model_validate(item)
        for item in _jsonl(root / "specifications" / "eval-specifications.jsonl")
    )
    judgments = tuple(
        EvidenceJudgmentRecord.model_validate(item)
        for item in _jsonl(root / "judgments" / "evidence-assessments.jsonl")
    )
    references_path = root / "references" / "answer-examples.jsonl"
    references = (
        tuple(
            ReferenceAnswerRecord.model_validate(item)
            for item in _jsonl(references_path)
        )
        if references_path.exists()
        else ()
    )

    by_problem: dict[str, list[EvidenceAssessment]] = {}
    for record in judgments:
        by_problem.setdefault(record.problem_id, []).append(record.assessment)
    specifications = tuple(
        specification.model_copy(
            update={
                "evidence_assessments": tuple(
                    sorted(
                        by_problem.get(specification.problem_id, ()),
                        key=lambda item: item.evidence_ref,
                    )
                )
            }
        )
        for specification in raw_specs
    )
    return TaskDataset(
        manifest=manifest,
        world=world,
        problems=problems,
        specifications=specifications,
        evidence_judgments=judgments,
        reference_answers=references,
    )


def verify_world_artifacts(dataset_root: Path, world: WorldManifest) -> None:
    for artifact in world.artifacts:
        path = (dataset_root / artifact.path).resolve()
        if not path.is_file():
            raise ValueError(f"missing world artifact: {path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != artifact.sha256:
            raise ValueError(f"world artifact fingerprint mismatch: {artifact.role}")
        record_count = sum(
            1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
        )
        if record_count != artifact.record_count:
            raise ValueError(f"world artifact record count mismatch: {artifact.role}")


def _jsonl(path: Path) -> tuple[Mapping[str, object], ...]:
    return tuple(
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def _unique(
    items: Sequence[BaseModel], field: str, label: str
) -> dict[str, BaseModel]:
    output: dict[str, BaseModel] = {}
    for item in items:
        value = str(getattr(item, field))
        if value in output:
            raise ValueError(f"duplicate {label} id: {value}")
        output[value] = item
    return output
