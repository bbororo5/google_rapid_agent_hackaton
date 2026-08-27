from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from launchpilot.evaluation.contracts import EvidenceJudgment


class CurrentQrel(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_ref: str
    judgment: EvidenceJudgment
    relevance_grade: int = Field(ge=0, le=3)


class EvidencePreview(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_ref: str
    document_id: str
    title: str
    excerpt: str


class PriorityReviewItem(BaseModel):
    """A review task only; decisions belong in a separate adjudication artifact."""

    model_config = ConfigDict(frozen=True)

    query_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    current_analysis_task: str = Field(min_length=1)
    current_is_negative: bool
    campaign_ref: str
    review_reasons: tuple[str, ...] = Field(min_length=1)
    current_qrels: tuple[CurrentQrel, ...] = ()
    current_expected_document_ids: tuple[str, ...] = ()
    current_expected_numbers: tuple[str, ...] = ()
    current_causal_triad: dict[str, str] = Field(default_factory=dict)
    evidence_previews: tuple[EvidencePreview, ...] = ()


class PriorityReviewQueue(BaseModel):
    model_config = ConfigDict(frozen=True)

    queue_version: str
    source_dataset: str
    source_fingerprint: str
    fingerprint: str
    items: tuple[PriorityReviewItem, ...]


def build_v3_priority_review_queue(
    cases: Sequence[Mapping[str, Any]],
    qrels: Sequence[Mapping[str, Any]],
    generation_truth: Sequence[Mapping[str, Any]],
    documents: Sequence[Mapping[str, Any]],
    *,
    source_dataset: str,
    queue_version: str = "v3-priority-review-v1",
) -> PriorityReviewQueue:
    case_by_id = _unique_rows(cases, "case_id", "case")
    truth_by_id = _unique_rows(generation_truth, "case_id", "generation truth")
    if set(case_by_id) != set(truth_by_id):
        raise ValueError("case and generation-truth ids must match exactly")
    orphan_qrels = sorted(
        {str(item["case_id"]) for item in qrels} - case_by_id.keys()
    )
    if orphan_qrels:
        raise ValueError(f"qrels reference unknown cases: {orphan_qrels}")
    qrels_by_case = _qrels_by_case(qrels)
    documents_by_ref, documents_by_id = _document_lookups(documents)

    items = []
    for query_id, case in sorted(case_by_id.items()):
        is_negative = bool(case.get("is_negative", False))
        is_comparison = case.get("analysis_task") == "cross_campaign_comparison"
        if not is_negative and not is_comparison:
            continue
        truth = truth_by_id[query_id]
        current_qrels = qrels_by_case.get(query_id, ())
        expected_ids = tuple(
            sorted(str(item) for item in truth.get("expected_document_ids", ()))
        )
        reasons = []
        if is_negative:
            reasons.append("confirm_answerability_and_abstention")
        if is_comparison:
            reasons.append("confirm_cross_campaign_scope_and_required_facts")
            if len(current_qrels) < 2 or len(expected_ids) < 2:
                reasons.append("expand_incomplete_multi_source_evidence")
        evidence_refs = {item.evidence_ref for item in current_qrels}
        previews = {
            preview.evidence_ref: preview
            for preview in (
                _preview(documents_by_ref.get(evidence_ref))
                for evidence_ref in evidence_refs
            )
            if preview is not None
        }
        for document_id in expected_ids:
            preview = _preview(documents_by_id.get(document_id))
            if preview is not None:
                previews.setdefault(preview.evidence_ref, preview)
        items.append(
            PriorityReviewItem(
                query_id=query_id,
                query=str(case["query"]),
                current_analysis_task=str(case["analysis_task"]),
                current_is_negative=is_negative,
                campaign_ref=str(case.get("campaign_ref", "")),
                review_reasons=tuple(reasons),
                current_qrels=current_qrels,
                current_expected_document_ids=expected_ids,
                current_expected_numbers=tuple(
                    str(item) for item in truth.get("expected_numbers", ())
                ),
                current_causal_triad={
                    str(key): str(value)
                    for key, value in truth.get("causal_triad", {}).items()
                },
                evidence_previews=tuple(previews[key] for key in sorted(previews)),
            )
        )
    source_fingerprint = _fingerprint(
        {
            "source_dataset": source_dataset,
            "cases": sorted(cases, key=lambda item: str(item["case_id"])),
            "qrels": sorted(
                qrels,
                key=lambda item: (str(item["case_id"]), str(item["corpus_ref"])),
            ),
            "generation_truth": sorted(
                generation_truth, key=lambda item: str(item["case_id"])
            ),
            "documents": sorted(documents, key=lambda item: str(item["id"])),
        }
    )
    fingerprint = _fingerprint(
        {
            "queue_version": queue_version,
            "source_fingerprint": source_fingerprint,
            "items": [item.model_dump(mode="json") for item in items],
        }
    )
    return PriorityReviewQueue(
        queue_version=queue_version,
        source_dataset=source_dataset,
        source_fingerprint=source_fingerprint,
        fingerprint=fingerprint,
        items=tuple(items),
    )


def load_v3_priority_review_queue(golden_root: Path) -> PriorityReviewQueue:
    return build_v3_priority_review_queue(
        _jsonl(golden_root / "queries" / "cases.jsonl"),
        _jsonl(golden_root / "judgments" / "qrels.jsonl"),
        _jsonl(golden_root / "judgments" / "generation_ground_truth.jsonl"),
        _jsonl(golden_root / "corpus" / "documents.jsonl"),
        source_dataset=golden_root.name,
    )


def write_priority_review_queue(path: Path, queue: PriorityReviewQueue) -> None:
    metadata_path = path.with_suffix(".manifest.json")
    if path.exists() or metadata_path.exists():
        raise FileExistsError(f"review queue already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(item.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
            + "\n"
            for item in queue.items
        ),
        encoding="utf-8",
    )
    metadata_path.write_text(
        json.dumps(
            {
                "queue_version": queue.queue_version,
                "source_dataset": queue.source_dataset,
                "source_fingerprint": queue.source_fingerprint,
                "fingerprint": queue.fingerprint,
                "item_count": len(queue.items),
                "status": "awaiting_human_review",
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _unique_rows(
    rows: Sequence[Mapping[str, Any]], key: str, label: str
) -> dict[str, Mapping[str, Any]]:
    output: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        row_id = str(row[key])
        if row_id in output:
            raise ValueError(f"duplicate {label} id: {row_id}")
        output[row_id] = row
    return output


def _qrels_by_case(
    qrels: Sequence[Mapping[str, Any]],
) -> dict[str, tuple[CurrentQrel, ...]]:
    output: dict[str, list[CurrentQrel]] = defaultdict(list)
    seen: dict[tuple[str, str], CurrentQrel] = {}
    for qrel in qrels:
        query_id = str(qrel["case_id"])
        evidence_ref = str(qrel["corpus_ref"])
        grade = int(qrel.get("relevance", 1))
        current = CurrentQrel(
            evidence_ref=evidence_ref,
            judgment=(
                EvidenceJudgment.KNOWN_RELEVANT
                if grade > 0
                else EvidenceJudgment.KNOWN_IRRELEVANT
            ),
            relevance_grade=grade,
        )
        key = (query_id, evidence_ref)
        if key in seen and seen[key] != current:
            raise ValueError(f"conflicting qrels for {query_id}/{evidence_ref}")
        if key not in seen:
            seen[key] = current
            output[query_id].append(current)
    return {
        query_id: tuple(sorted(items, key=lambda item: item.evidence_ref))
        for query_id, items in output.items()
    }


def _document_lookups(
    documents: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    by_ref: dict[str, Mapping[str, Any]] = {}
    by_id: dict[str, Mapping[str, Any]] = {}
    for document in documents:
        document_id = str(document["id"])
        document_ref = str(document["document_key"])
        if document_id in by_id or document_ref in by_ref:
            raise ValueError(f"duplicate document id or ref: {document_id}/{document_ref}")
        by_id[document_id] = document
        by_ref[document_ref] = document
    return by_ref, by_id


def _preview(document: Mapping[str, Any] | None) -> EvidencePreview | None:
    if document is None:
        return None
    return EvidencePreview(
        evidence_ref=str(document["document_key"]),
        document_id=str(document["id"]),
        title=str(document.get("title", "")),
        excerpt=str(document.get("content", ""))[:500],
    )


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
