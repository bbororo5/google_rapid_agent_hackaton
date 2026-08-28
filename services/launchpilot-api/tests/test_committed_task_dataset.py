from __future__ import annotations

from pathlib import Path

from launchpilot.evaluation.contracts import ReviewStatus
from launchpilot.evaluation.task_dataset import (
    load_task_dataset,
    verify_world_artifacts,
)

from launchpilot.evaluation.task_dataset_cli import inspect_task_dataset

ROOT = Path(__file__).parents[1]
DATASET_ROOT = ROOT / "evals" / "datasets" / "marketing-ops-task-v1"


def test_committed_task_dataset_is_valid_and_explicitly_not_release_ready() -> None:
    dataset = load_task_dataset(DATASET_ROOT)
    verify_world_artifacts(DATASET_ROOT, dataset.world)

    assert dataset.manifest.problem_count == 150
    assert dataset.manifest.specification_count == 150
    assert dataset.manifest.evidence_judgment_count == 121
    assert dataset.manifest.reference_answer_count == 150
    assert dataset.manifest.release_ready is False
    assert dataset.manifest.lifecycle == "frontier"
    assert all(
        specification.review_status == ReviewStatus.NEEDS_REVIEW
        for specification in dataset.specifications
    )
    assert all(
        reference.grading_authority is False
        for reference in dataset.reference_answers
    )


def test_task_dataset_contains_no_expected_tool_or_route_truth() -> None:
    dataset = load_task_dataset(DATASET_ROOT)

    for problem in dataset.problems:
        payload = problem.model_dump(mode="json")
        assert "expected_tool" not in payload
        assert "route" not in payload
        assert problem.portfolio.value == "frontier"
        assert problem.world_id == dataset.world.world_id
    for specification in dataset.specifications:
        payload = specification.model_dump(mode="json")
        assert "expected_tool" not in payload
        assert "route" not in payload


def test_incomplete_legacy_evidence_is_preserved_as_a_knowledge_state() -> None:
    dataset = load_task_dataset(DATASET_ROOT)
    specs = {item.problem_id: item for item in dataset.specifications}

    comparison = specs["det_comp_c0001_c0002"]
    assert len(comparison.evidence_assessments) == 1
    assert comparison.evidence_assessments[0].supports_fact_ids == ()

    negative = specs["det_neg_01"]
    assert negative.evidence_assessments == ()
    assert negative.answerability.value == "insufficient_evidence"
    assert negative.expected_behaviors[0].value == "abstain"


def test_dataset_readiness_report_blocks_release_without_human_review() -> None:
    report = inspect_task_dataset(DATASET_ROOT)

    assert report["release_ready"] is False
    assert report["review_statuses"] == {"needs_review": 150}
    assert report["problem_sources"] == {"synthetic": 150}
    assert "150 specifications need review" in report["release_blockers"]
    assert "no production-sourced problems" in report["release_blockers"]
