from __future__ import annotations

import json
from pathlib import Path

import pytest

from launchpilot.evaluation.contracts import (
    Answerability,
    ExpectedBehavior,
    InformationModality,
    PortfolioRole,
    ReviewStatus,
)
from launchpilot.evaluation.portfolio.benchmark_builder import (
    build_benchmark_portfolio,
    load_cases,
)
from launchpilot.evaluation.portfolio.v2_adapter import (
    convert_v2_cases,
    write_portfolio_contracts,
)

ROOT = Path(__file__).parents[1]
GOLDEN = ROOT / "evals/golden/golden-v2"


def test_v2_frozen_candidate_converts_to_separate_query_and_specs(
    tmp_path: Path,
) -> None:
    cases = load_cases(GOLDEN / "queries/cases.jsonl")
    manifest = build_benchmark_portfolio(cases)
    frozen_ids = {item.case_id for item in manifest.frozen_records}
    queries, specs = convert_v2_cases(
        cases,
        _jsonl(GOLDEN / "judgments/qrels.jsonl"),
        case_ids=frozen_ids,
        portfolio=PortfolioRole.FROZEN,
    )

    assert len(queries) == len(specs) == 64
    assert {item.query_id for item in queries} == {item.query_id for item in specs}
    assert all(item.portfolio == PortfolioRole.FROZEN for item in queries)
    assert sum(item.review_status == ReviewStatus.AUTO_VALIDATED for item in specs) == 48
    assert sum(item.review_status == ReviewStatus.NEEDS_REVIEW for item in specs) == 16
    assert all("tool" not in item.model_dump_json().lower() for item in queries)

    causal_query = next(
        item for item in queries if item.query_id.endswith("causal-overclaim")
    )
    causal_spec = next(
        item for item in specs if item.query_id == causal_query.query_id
    )
    assert causal_query.characteristics.modalities == (InformationModality.MIXED,)
    assert causal_spec.answerability == Answerability.INSUFFICIENT_EVIDENCE
    assert causal_spec.expected_behaviors == (ExpectedBehavior.ABSTAIN,)

    output = tmp_path / "frozen-v0-candidate"
    write_portfolio_contracts(output, queries, specs)
    written_manifest = json.loads((output / "manifest.json").read_text())
    assert written_manifest["query_count"] == 64
    assert written_manifest["contract_schema_version"] == "architecture-eval-v1"
    assert written_manifest["portfolio_role"] == "frozen"
    assert written_manifest["query_source_distribution"] == {"synthetic": 64}
    assert written_manifest["review_status_distribution"] == {
        "auto_validated": 48,
        "needs_review": 16,
    }


def test_v2_holdout_remains_review_gated_and_behavior_explicit() -> None:
    cases = load_cases(GOLDEN / "queries/cases.jsonl")
    manifest = build_benchmark_portfolio(cases)
    holdout_ids = {item.case_id for item in manifest.holdout_records}
    queries, specs = convert_v2_cases(
        cases,
        _jsonl(GOLDEN / "judgments/qrels.jsonl"),
        case_ids=holdout_ids,
        portfolio=PortfolioRole.HOLDOUT,
    )

    assert len(queries) == len(specs) == 50
    assert all(item.portfolio == PortfolioRole.HOLDOUT for item in queries)
    assert all(item.review_status == ReviewStatus.NEEDS_REVIEW for item in specs)
    assert all(item.expected_behaviors == (ExpectedBehavior.ABSTAIN,) for item in specs)
    assert all(not item.evidence_assessments for item in specs)


def test_converter_rejects_unknown_case_ids() -> None:
    cases = load_cases(GOLDEN / "queries/cases.jsonl")

    try:
        convert_v2_cases(
            cases,
            _jsonl(GOLDEN / "judgments/qrels.jsonl"),
            case_ids={"does.not.exist"},
            portfolio=PortfolioRole.FROZEN,
        )
    except ValueError as error:
        assert "unknown selected case ids" in str(error)
    else:
        raise AssertionError("unknown case id must be rejected")


def test_writer_rejects_duplicate_query_ids(tmp_path: Path) -> None:
    cases = load_cases(GOLDEN / "queries/cases.jsonl")
    case_id = str(cases[0]["case_id"])
    queries, specs = convert_v2_cases(
        cases,
        _jsonl(GOLDEN / "judgments/qrels.jsonl"),
        case_ids={case_id},
        portfolio=PortfolioRole.FROZEN,
    )

    with pytest.raises(ValueError, match="query ids must be unique"):
        write_portfolio_contracts(tmp_path / "duplicates", queries * 2, specs)


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]
