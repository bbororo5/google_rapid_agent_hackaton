from pathlib import Path

import pytest

from launchpilot.evaluation import GoldenRetrievalCase, load_golden_dataset


def test_example_golden_dataset_obeys_authoring_contract() -> None:
    dataset = load_golden_dataset(
        Path(__file__).parents[1] / "evals" / "golden_dataset_v1.example.jsonl"
    )

    assert [case.case_id for case in dataset] == [
        "structured.meta-clicks-after-fatigue",
        "textual.meta-creative-fatigue",
    ]
    assert dataset[0].expected_facts[0].value == "3676"
    assert dataset[1].expected_evidence[0].passage.startswith("7월 17일")


def test_task_type_requires_matching_ground_truth() -> None:
    with pytest.raises(ValueError, match="structured cases require expected_facts"):
        GoldenRetrievalCase.model_validate(
            {
                "case_id": "invalid.structured-case",
                "query": "클릭 수는?",
                "task_type": "structured",
                "scope": {"scenario_id": "scenario", "campaign_ref": "campaign"},
            }
        )
