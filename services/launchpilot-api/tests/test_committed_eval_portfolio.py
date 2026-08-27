from __future__ import annotations

import json
from pathlib import Path

from launchpilot.evaluation.portfolio.review_queue import (
    load_v3_priority_review_queue,
    write_priority_review_queue,
)

ROOT = Path(__file__).parents[1]


def test_archived_datasets_cannot_feed_active_evaluation() -> None:
    registry = json.loads(
        (ROOT / "evals/golden/dataset-registry.json").read_text(encoding="utf-8")
    )
    required_prohibitions = {
        "active_benchmark_selection",
        "active_gold_migration",
        "regression_seed_selection",
        "holdout_construction",
        "architecture_release_decision",
    }

    for dataset_id in ("golden-v1", "golden-v2"):
        policy = registry["datasets"][dataset_id]
        assert policy["lifecycle"] == "archived"
        assert policy["allowed_uses"] == ["historical_reproduction"]
        assert set(policy["prohibited_uses"]) == required_prohibitions

    assert registry["datasets"]["golden-v3"]["lifecycle"] == "current_fixture"
    assert registry["datasets"]["golden-v3"]["release_ready"] is False


def test_committed_v3_review_queue_matches_source_lineage(tmp_path: Path) -> None:
    queue = load_v3_priority_review_queue(ROOT / "evals/golden/golden-v3")
    regenerated = tmp_path / "v3-priority-review.jsonl"
    write_priority_review_queue(regenerated, queue)
    committed = ROOT / "evals/portfolio/review/v3-priority-review.jsonl"

    assert regenerated.read_bytes() == committed.read_bytes()
    assert regenerated.with_suffix(".manifest.json").read_bytes() == (
        committed.with_suffix(".manifest.json").read_bytes()
    )
