from __future__ import annotations

import json
from pathlib import Path

from launchpilot.evaluation.contracts import PortfolioRole
from launchpilot.evaluation.portfolio.benchmark_builder import (
    build_benchmark_portfolio,
    load_cases,
)
from launchpilot.evaluation.portfolio.review_queue import (
    load_v3_priority_review_queue,
    write_priority_review_queue,
)
from launchpilot.evaluation.portfolio.v2_adapter import (
    convert_v2_cases,
    write_portfolio_contracts,
)

ROOT = Path(__file__).parents[1]
V2 = ROOT / "evals/golden/golden-v2"
PORTFOLIO = ROOT / "evals/portfolio/golden-v2-portfolio-v0"


def test_committed_v2_selection_and_contracts_match_deterministic_build(
    tmp_path: Path,
) -> None:
    cases = load_cases(V2 / "queries/cases.jsonl")
    qrels = _jsonl(V2 / "judgments/qrels.jsonl")
    selection = build_benchmark_portfolio(cases)
    assert json.loads((PORTFOLIO / "selection-manifest.json").read_text()) == json.loads(
        json.dumps(selection.to_dict(), ensure_ascii=False)
    )

    components = {
        item.case_id: item.leakage_component_id for item in selection.records
    }
    for name, role, case_ids in (
        (
            "frozen-candidate",
            PortfolioRole.FROZEN,
            {item.case_id for item in selection.frozen_records},
        ),
        (
            "holdout-candidate",
            PortfolioRole.HOLDOUT,
            {item.case_id for item in selection.holdout_records},
        ),
    ):
        queries, specifications = convert_v2_cases(
            cases,
            qrels,
            case_ids=case_ids,
            leakage_component_by_case=components,
            portfolio=role,
        )
        regenerated = tmp_path / name
        write_portfolio_contracts(regenerated, queries, specifications)
        for filename in (
            "queries.jsonl",
            "eval-specifications.jsonl",
            "manifest.json",
        ):
            assert (regenerated / filename).read_bytes() == (
                PORTFOLIO / name / filename
            ).read_bytes()


def test_committed_v3_review_queue_matches_source_lineage(tmp_path: Path) -> None:
    queue = load_v3_priority_review_queue(ROOT / "evals/golden/golden-v3")
    regenerated = tmp_path / "v3-priority-review.jsonl"
    write_priority_review_queue(regenerated, queue)
    committed = ROOT / "evals/portfolio/review/v3-priority-review.jsonl"

    assert regenerated.read_bytes() == committed.read_bytes()
    assert regenerated.with_suffix(".manifest.json").read_bytes() == (
        committed.with_suffix(".manifest.json").read_bytes()
    )


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]
