from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from launchpilot.evaluation.task_dataset import (
    load_task_dataset,
    verify_world_artifacts,
)


def test_task_dataset_loads_physically_separated_problem_spec_and_judgment(
    tmp_path: Path,
) -> None:
    world_source = tmp_path / "source-documents.jsonl"
    world_source.write_text('{"id":"doc-1"}\n', encoding="utf-8")
    root = tmp_path / "dataset"
    _json(
        root / "manifest.json",
        {
            "dataset_id": "task-fixture",
            "dataset_version": "v1",
            "lifecycle": "frontier",
            "release_ready": False,
            "source_fixture": "legacy-v3",
            "world_id": "world-v1",
            "problem_count": 1,
            "specification_count": 1,
            "evidence_judgment_count": 1,
            "reference_answer_count": 1,
            "human_review_status": "awaiting_human_review",
        },
    )
    _json(
        root / "world" / "manifest.json",
        {
            "world_id": "world-v1",
            "world_version": "v1",
            "source_type": "synthetic",
            "description": "test world",
            "artifacts": [
                {
                    "role": "documents",
                    "path": "../source-documents.jsonl",
                    "sha256": hashlib.sha256(world_source.read_bytes()).hexdigest(),
                    "record_count": 1,
                }
            ],
        },
    )
    _jsonl(
        root / "problems" / "problems.jsonl",
        [
            {
                "problem_id": "problem.001",
                "user_utterance": "예산 변경 이유를 알려줘",
                "information_need": "예산 변경의 원인을 확인한다.",
                "world_id": "world-v1",
                "source": "synthetic",
                "portfolio": "frontier",
                "characteristics": {
                    "modalities": ["mixed"],
                    "task_shape": "lookup",
                },
            }
        ],
    )
    _jsonl(
        root / "specifications" / "eval-specifications.jsonl",
        [
            {
                "spec_id": "problem.001.spec",
                "spec_version": "v1",
                "problem_id": "problem.001",
                "answerability": "answerable",
                "required_facts": [
                    {
                        "fact_id": "reason",
                        "description": "예산 변경 원인",
                        "grader": "human",
                    }
                ],
                "expected_behaviors": ["answer"],
                "review_status": "needs_review",
                "grader_rubric_version": "task-facts-v1",
            }
        ],
    )
    _jsonl(
        root / "judgments" / "evidence-assessments.jsonl",
        [
            {
                "problem_id": "problem.001",
                "assessment": {
                    "evidence_ref": "doc-1",
                    "judgment": "known_relevant",
                    "relevance_grade": 2,
                    "supports_fact_ids": ["reason"],
                },
            }
        ],
    )
    _jsonl(
        root / "references" / "answer-examples.jsonl",
        [
            {
                "problem_id": "problem.001",
                "answer": "예산은 소진 속도 때문에 조정되었습니다.",
                "status": "legacy_synthetic_example",
                "grading_authority": False,
                "provenance": "legacy-v3",
            }
        ],
    )

    dataset = load_task_dataset(root)

    assert dataset.problems[0].information_need == "예산 변경의 원인을 확인한다."
    assert dataset.specifications[0].evidence_assessments[0].supports_fact_ids == (
        "reason",
    )
    assert dataset.reference_answers[0].grading_authority is False
    assert len(dataset.fingerprint) == 64
    verify_world_artifacts(root, dataset.world)


def test_task_dataset_rejects_judgment_for_unknown_problem(tmp_path: Path) -> None:
    # Reuse the contract directly to keep this failure focused on cross-artifact refs.
    from launchpilot.evaluation.task_dataset import EvidenceJudgmentRecord

    with pytest.raises(ValidationError):
        EvidenceJudgmentRecord.model_validate(
            {
                "assessment": {
                    "evidence_ref": "doc",
                    "judgment": "known_relevant",
                    "relevance_grade": 1,
                }
            }
        )


def _json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _jsonl(path: Path, payloads: list[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(payload, ensure_ascii=False) + "\n" for payload in payloads),
        encoding="utf-8",
    )
