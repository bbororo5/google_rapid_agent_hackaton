from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from launchpilot.evaluation.portfolio.benchmark_builder import (
    PortfolioPolicy,
    assert_no_portfolio_leakage,
    build_benchmark_portfolio,
    leakage_keys,
    load_cases,
    template_style_key,
    write_benchmark_manifest,
)

GOLDEN_V2_CASES = (
    Path(__file__).parents[1]
    / "evals"
    / "golden"
    / "golden-v2"
    / "queries"
    / "cases.jsonl"
)


def test_real_v2_portfolio_is_deterministic_compact_and_leakage_disjoint(
    tmp_path: Path,
) -> None:
    cases = load_cases(GOLDEN_V2_CASES)

    first = build_benchmark_portfolio(cases)
    second = build_benchmark_portfolio(tuple(reversed(cases)))

    assert first == second
    assert first.source_case_count == 680
    assert len(first.records) == 680
    assert len(first.frozen_records) == 64
    assert len(first.holdout_records) == 50
    assert first.holdout_target_delta == 0
    assert first.leakage_component_count == 2
    assert first.largest_leakage_component_size == 630
    assert first.warnings == (
        "source_dataset_has_giant_leakage_component",
        "holdout_is_not_distribution_representative",
        "holdout_is_fully_pending_human_review",
        "frozen_candidate_contains_review_gated_cases",
    )
    assert_no_portfolio_leakage(first)
    output = tmp_path / "selection-manifest.json"
    write_benchmark_manifest(output, first)
    assert '"source_case_count": 680' in output.read_text()
    with pytest.raises(FileExistsError):
        write_benchmark_manifest(output, first)


def test_review_required_safety_cases_are_never_silently_promoted() -> None:
    manifest = build_benchmark_portfolio(load_cases(GOLDEN_V2_CASES))
    frozen_safety = [
        record
        for record in manifest.frozen_records
        if record.candidate_class == "high_value_safety"
    ]

    assert len(frozen_safety) == 16
    assert all(record.human_review_required for record in frozen_safety)
    assert all(record.readiness == "pending_human_review" for record in frozen_safety)
    assert all(
        "human_review_gate_preserved" in record.selection_reasons
        for record in frozen_safety
    )
    assert set(frozen_safety) <= set(manifest.human_review_queue)
    assert all(
        record.readiness == "ready"
        for record in manifest.frozen_records
        if record.candidate_class == "auto_validatable"
    )


def test_selection_ignores_tool_and_route_hints() -> None:
    cases = list(load_cases(GOLDEN_V2_CASES))
    hinted_cases = deepcopy(cases)
    for index, case in enumerate(hinted_cases):
        case["expected_retriever"] = "dense" if index % 2 else "graph"
        case["expected_route"] = "some-architecture-specific-route"

    plain = build_benchmark_portfolio(cases)
    hinted = build_benchmark_portfolio(hinted_cases)

    assert [record.case_id for record in plain.frozen_records] == [
        record.case_id for record in hinted.frozen_records
    ]
    assert [record.case_id for record in plain.holdout_records] == [
        record.case_id for record in hinted.holdout_records
    ]


def test_leakage_keys_cover_declared_entity_source_and_template_style_groups() -> None:
    cases = load_cases(GOLDEN_V2_CASES)
    case = next(item for item in cases if item["case_id"].startswith("structured."))
    keys = leakage_keys(case)

    assert any(key.startswith("declared:") for key in keys)
    assert any(key.startswith("entity:") for key in keys)
    assert any(key.startswith("source:") for key in keys)
    assert any(key.startswith("template_style:") for key in keys)
    assert template_style_key("structured.c0001-c0013.campaign-impressions") == (
        "structured.c#-c#.campaign-impressions"
    )


def test_policy_is_configurable_without_relaxing_the_review_gate() -> None:
    policy = PortfolioPolicy(
        frozen_auto_validated_limit=7,
        frozen_safety_review_limit=3,
        holdout_target_size=50,
        selection_salt="focused-test",
    )

    manifest = build_benchmark_portfolio(load_cases(GOLDEN_V2_CASES), policy)

    assert len(manifest.frozen_records) == 10
    assert len(manifest.holdout_records) == 50
    assert sum(record.human_review_required for record in manifest.frozen_records) == 3
    serialized = manifest.to_dict()
    assert serialized["selection_summary"]["human_review_queue_size"] >= 3
    assert serialized["leakage_summary"]["holdout_target_delta"] == 0
    assert "leakage_keys" not in serialized["records"][0]
    assert serialized["records"][0]["leakage_key_count"] > 0
    assert len(serialized["records"]) == 60
    assert serialized["omitted_record_summary"]["count"] == 620

    diagnostic = manifest.to_dict(
        include_leakage_keys=True,
        include_unselected_records=True,
    )
    assert len(diagnostic["records"]) == 680
    assert diagnostic["records"][0]["leakage_keys"]
