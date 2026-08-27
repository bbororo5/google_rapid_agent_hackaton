from __future__ import annotations

import json
from pathlib import Path

import pytest

from launchpilot.evaluation.portfolio.review_queue import (
    build_v3_priority_review_queue,
    load_v3_priority_review_queue,
    write_priority_review_queue,
)

ROOT = Path(__file__).parents[1]


def test_v3_priority_queue_exposes_unresolved_cases_without_auto_judging(
    tmp_path: Path,
) -> None:
    queue = load_v3_priority_review_queue(ROOT / "evals/golden/golden-v3")

    assert len(queue.items) == 39
    assert sum(item.current_is_negative for item in queue.items) == 29
    comparison_items = [
        item
        for item in queue.items
        if item.current_analysis_task == "cross_campaign_comparison"
    ]
    assert len(comparison_items) == 10
    assert all(
        "expand_incomplete_multi_source_evidence" in item.review_reasons
        for item in comparison_items
    )
    assert all(item.current_qrels for item in comparison_items)
    assert all(item.evidence_previews for item in comparison_items)

    output = tmp_path / "priority.jsonl"
    write_priority_review_queue(output, queue)
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    manifest = json.loads(
        output.with_suffix(".manifest.json").read_text(encoding="utf-8")
    )
    assert len(rows) == 39
    assert manifest["fingerprint"] == queue.fingerprint
    assert manifest["source_fingerprint"] == queue.source_fingerprint
    assert manifest["status"] == "awaiting_human_review"
    with pytest.raises(FileExistsError):
        write_priority_review_queue(output, queue)


def test_v3_priority_queue_is_deterministic() -> None:
    root = ROOT / "evals/golden/golden-v3"
    left = load_v3_priority_review_queue(root)
    right = load_v3_priority_review_queue(root)

    assert left == right


def test_source_changes_affect_lineage_and_invalid_relations_are_rejected() -> None:
    cases, qrels, truth, documents = _small_fixture()
    original = build_v3_priority_review_queue(
        cases, qrels, truth, documents, source_dataset="fixture-v1"
    )
    changed = build_v3_priority_review_queue(
        cases,
        [{**qrels[0], "relevance": 2}],
        truth,
        documents,
        source_dataset="fixture-v1",
    )
    assert original.source_fingerprint != changed.source_fingerprint
    assert original.fingerprint != changed.fingerprint

    with pytest.raises(ValueError, match="duplicate case"):
        build_v3_priority_review_queue(
            [*cases, cases[0]], qrels, truth, documents, source_dataset="fixture-v1"
        )
    with pytest.raises(ValueError, match="unknown cases"):
        build_v3_priority_review_queue(
            cases,
            [{**qrels[0], "case_id": "orphan"}],
            truth,
            documents,
            source_dataset="fixture-v1",
        )


def _small_fixture():
    cases = [
        {
            "case_id": "comparison.one",
            "query": "compare two campaigns",
            "analysis_task": "cross_campaign_comparison",
            "campaign_ref": "C0001",
            "is_negative": False,
        }
    ]
    qrels = [
        {"case_id": "comparison.one", "corpus_ref": "c0001:memo_01", "relevance": 1}
    ]
    truth = [
        {
            "case_id": "comparison.one",
            "expected_document_ids": ["doc-1"],
            "expected_numbers": ["10"],
            "causal_triad": {"trigger": "drop"},
        }
    ]
    documents = [
        {
            "id": "doc-1",
            "document_key": "c0001:memo_01",
            "title": "memo",
            "content": "supporting evidence",
        }
    ]
    return cases, qrels, truth, documents
