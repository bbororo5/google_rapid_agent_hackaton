from __future__ import annotations

import json
from pathlib import Path

import yaml

GOLDEN_ROOT = Path(__file__).parents[1] / "evals" / "golden" / "golden-v2"
TAXONOMY_PATH = Path(__file__).parents[1] / "evals" / "taxonomy.yaml"


def _jsonl(relative_path: str) -> list[dict[str, object]]:
    path = GOLDEN_ROOT / relative_path
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_marketing_golden_v2_has_the_expected_profiles_and_splits() -> None:
    manifest = json.loads((GOLDEN_ROOT / "manifest.json").read_text(encoding="utf-8"))
    cases = _jsonl("queries/cases.jsonl")
    splits = json.loads(
        (GOLDEN_ROOT / "splits" / "splits.json").read_text(encoding="utf-8")
    )

    assert manifest["golden_version"] == "golden-v2"
    assert manifest["total_cases"] == 680
    assert manifest["case_distribution"] == {
        "adversarial": 80,
        "ambiguous": 50,
        "entity_semantic": 30,
        "lexical_identifier": 90,
        "mixed_structured_semantic": 50,
        "no_answer": 50,
        "semantic": 50,
        "structured_exact": 280,
    }
    split_distribution = manifest["split_distribution"]
    assert sum(split_distribution.values()) == 680
    assert manifest["retrieval_configuration"] is None
    assert manifest["taxonomy_version"] == "marketing-retrieval-taxonomy-v1"
    assert manifest["taxonomy_coverage_ready"] is True
    assert all("expected_retriever" not in case for case in cases)

    taxonomy_fields = {
        "marketing_domain",
        "analysis_task",
        "business_objective",
        "funnel_stage",
        "metric_family",
        "scope_type",
        "temporal_granularity",
        "difficulty",
        "evidence_type",
        "answer_mode",
        "language_style",
        "risk_types",
    }
    assert all(taxonomy_fields <= set(case) for case in cases)

    case_ids = {case["case_id"] for case in cases}
    split_sets = [set(ids) for ids in splits["cases"].values()]
    assert set.union(*split_sets) == case_ids
    assert sum(len(ids) for ids in split_sets) == len(case_ids)

    split_by_case = {
        case_id: split for split, ids in splits["cases"].items() for case_id in ids
    }
    group_splits: dict[str, set[str]] = {}
    for case in cases:
        for group_id in case["leakage_group_ids"]:
            group_splits.setdefault(group_id, set()).add(split_by_case[case["case_id"]])
    assert all(len(group) == 1 for group in group_splits.values())


def test_golden_v2_all_positive_qrels_resolve_to_corpus() -> None:
    cases = _jsonl("queries/cases.jsonl")
    qrels = _jsonl("judgments/qrels.jsonl")
    corpus = _jsonl("corpus/observations.jsonl")
    documents = _jsonl("corpus/documents.jsonl")

    case_ids = {case["case_id"] for case in cases}
    corpus_refs = {record["corpus_ref"] for record in (*corpus, *documents)}

    assert len(case_ids) == 680
    assert len(qrels) == 3537
    assert len(corpus) == 3097
    assert len(documents) == 900
    assert {qrel["corpus_ref"] for qrel in qrels} <= corpus_refs
    assert all(qrel["case_id"] in case_ids for qrel in qrels)
    assert all(qrel["corpus_ref"] in corpus_refs for qrel in qrels)
    assert {qrel["source_type"] for qrel in qrels} == {"pg", "document"}


def test_golden_v2_document_spans_and_validation_pass() -> None:
    documents = _jsonl("corpus/documents.jsonl")
    spans = _jsonl("judgments/gold_spans.jsonl")
    excluded = _jsonl("review/excluded_items.jsonl")
    validation = json.loads(
        (GOLDEN_ROOT / "validation" / "validation_report.json").read_text(
            encoding="utf-8"
        )
    )

    documents_by_ref = {item["document_ref"]: item for item in documents}
    assert len(documents) == 900
    assert len(spans) == 130
    assert excluded == []
    assert all(
        documents_by_ref[span["document_ref"]]["content"][
            span["char_start"] : span["char_end"]
        ]
        == span["text"]
        for span in spans
    )
    assert validation["passed"] is True
    assert all(value == 0 for value in validation["checks"].values())
    assert validation["golden_version"] == "golden-v2"
    assert validation["human_review_required"] == 340


def test_golden_v2_satisfies_production_coverage_gates() -> None:
    taxonomy = yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))
    coverage = json.loads(
        (GOLDEN_ROOT / "validation" / "taxonomy_coverage.json").read_text(
            encoding="utf-8"
        )
    )
    catalog = GOLDEN_ROOT / "review" / "case_catalog.csv"

    assert taxonomy["taxonomy_version"] == "marketing-retrieval-taxonomy-v1"
    assert coverage["production_ready"] is True
    assert coverage["balance_gaps"] == []

    # Verify all critical slices are ready (>= 50 cases and >= 10 groups)
    for slice_item in coverage["critical_slice_readiness"]:
        assert slice_item["status"] == "ready", f"Slice {slice_item["slice"]} not ready"
        assert slice_item["case_count"] >= 50
        assert slice_item["distinct_groups"] >= 10

    assert catalog.read_bytes().startswith(b"\xef\xbb\xbf")
