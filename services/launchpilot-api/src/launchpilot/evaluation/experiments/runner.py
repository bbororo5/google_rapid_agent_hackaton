from __future__ import annotations

import hashlib
import json
import statistics
import time
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .chunking import chunk_documents
from .contracts import (
    EvaluationCase,
    EvaluationDocument,
    ExperimentCaseResult,
    ExperimentManifest,
    ExperimentResult,
    ExperimentStatus,
    GoldEvidence,
    SliceMetric,
)
from .metrics import retrieval_metrics
from .retrievers import (
    ExperimentDependencyUnavailable,
    RetrieverFactory,
)

_TAXONOMY_FIELDS = (
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
)


class RetrievalExperimentRunner:
    def __init__(self, factory: RetrieverFactory | None = None) -> None:
        self._factory = factory or RetrieverFactory()
        self._chunk_cache: dict[str, tuple[Any, ...]] = {}

    def run(
        self,
        manifest: ExperimentManifest,
        documents: Sequence[EvaluationDocument],
        cases: Sequence[EvaluationCase],
    ) -> ExperimentResult:
        started_at = datetime.now(UTC)
        selected_cases = tuple(case for case in cases if case.split == manifest.split)
        if not documents:
            return _blocked(
                manifest,
                started_at,
                "document corpus is empty",
                document_count=0,
                eligible_case_count=len(selected_cases),
            )
        if not selected_cases:
            return _blocked(
                manifest,
                started_at,
                f"no document-grounded cases exist in split: {manifest.split}",
                document_count=len(documents),
                eligible_case_count=0,
            )
        try:
            chunk_started = time.perf_counter()
            chunk_key = _chunk_cache_key(manifest, documents)
            cached_chunks = self._chunk_cache.get(chunk_key)
            if cached_chunks is None:
                cached_chunks = chunk_documents(
                    documents,
                    manifest.chunker,
                    semantic_encoder=self._factory.dense_encoder,
                )
                self._chunk_cache[chunk_key] = cached_chunks
            chunks = cached_chunks
            chunking_ms = (time.perf_counter() - chunk_started) * 1000
            retriever = self._factory.build(manifest.retriever)
        except (ExperimentDependencyUnavailable, RuntimeError) as error:
            return _blocked(
                manifest,
                started_at,
                str(error),
                document_count=len(documents),
                eligible_case_count=len(selected_cases),
            )
        indexing_started = time.perf_counter()
        retriever.index(chunks)
        indexing_ms = (time.perf_counter() - indexing_started) * 1000
        case_results = []
        for case in selected_cases:
            started = time.perf_counter()
            filters = (
                {"campaign_ref": case.campaign_ref}
                if (
                    case.campaign_ref
                    and manifest.retriever.search_scope == "campaign"
                )
                else None
            )
            hits = retriever.search(
                case.query,
                top_k=manifest.retriever.top_k,
                filters=filters,
            )
            latency_ms = (time.perf_counter() - started) * 1000
            case_results.append(
                ExperimentCaseResult(
                    case_id=case.case_id,
                    query_profile=case.query_profile,
                    taxonomy=case.taxonomy,
                    latency_ms=latency_ms,
                    retrieved=hits,
                    metrics=retrieval_metrics(
                        hits,
                        case.evidence,
                        top_k=manifest.retriever.top_k,
                    ),
                )
            )
        aggregate = _aggregate(case_results)
        aggregate["chunking_ms"] = chunking_ms
        aggregate["indexing_ms"] = indexing_ms
        return ExperimentResult(
            manifest=manifest,
            status=ExperimentStatus.COMPLETED,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            document_count=len(documents),
            chunk_count=len(chunks),
            eligible_case_count=len(selected_cases),
            aggregate_metrics=aggregate,
            slice_metrics=_slice_metrics(case_results),
            case_results=tuple(case_results),
        )


def load_golden_document_benchmark(
    golden_root: Path,
) -> tuple[tuple[EvaluationDocument, ...], tuple[EvaluationCase, ...], dict[str, Any]]:
    manifest = json.loads((golden_root / "manifest.json").read_text(encoding="utf-8"))
    document_rows = _jsonl(golden_root / "corpus" / "documents.jsonl")
    documents = tuple(_evaluation_document(item) for item in document_rows)
    document_refs = {item.document_ref for item in documents}
    case_rows = _jsonl(golden_root / "queries" / "cases.jsonl")
    qrels = _jsonl(golden_root / "judgments" / "qrels.jsonl")
    spans = _jsonl(golden_root / "judgments" / "gold_spans.jsonl")

    evidence_by_case: dict[str, list[GoldEvidence]] = defaultdict(list)
    span_keys: set[tuple[str, str]] = set()
    for item in spans:
        document_ref = str(item.get("document_ref") or item.get("corpus_ref"))
        if document_ref not in document_refs:
            continue
        case_id = str(item["case_id"])
        evidence_by_case[case_id].append(
            GoldEvidence(
                document_ref=document_ref,
                relevance=int(item.get("relevance", 3)),
                char_start=int(item["char_start"]),
                char_end=int(item["char_end"]),
            )
        )
        span_keys.add((case_id, document_ref))
    for item in qrels:
        document_ref = str(item["corpus_ref"])
        case_id = str(item["case_id"])
        if document_ref not in document_refs or (case_id, document_ref) in span_keys:
            continue
        evidence_by_case[case_id].append(
            GoldEvidence(
                document_ref=document_ref,
                relevance=int(item.get("relevance", 1)),
            )
        )

    cases = []
    for item in case_rows:
        case_id = str(item["case_id"])
        evidence = evidence_by_case.get(case_id)
        if not evidence:
            continue
        cases.append(
            EvaluationCase(
                case_id=case_id,
                query=str(item["query"]),
                query_profile=str(item["query_profile"]),
                split=str(item["split"]),
                campaign_ref=item.get("scope", {}).get("campaign_ref"),
                evidence=tuple(evidence),
                taxonomy={
                    field: item[field] for field in _TAXONOMY_FIELDS if field in item
                },
            )
        )
    return documents, tuple(cases), manifest


def _evaluation_document(item: dict[str, Any]) -> EvaluationDocument:
    document_ref = (
        item.get("document_ref") or item.get("corpus_ref") or item.get("source_ref")
    )
    text = item.get("content") or item.get("text")
    if not document_ref or not text:
        raise ValueError("document corpus rows require document_ref and content")
    excluded = {
        "document_ref",
        "corpus_ref",
        "source_ref",
        "content",
        "text",
        "title",
        "campaign_ref",
    }
    return EvaluationDocument(
        document_ref=str(document_ref),
        text=str(text),
        title=str(item.get("title", "")),
        campaign_ref=(str(item["campaign_ref"]) if item.get("campaign_ref") else None),
        metadata={key: value for key, value in item.items() if key not in excluded},
    )


def _aggregate(results: Sequence[ExperimentCaseResult]) -> dict[str, float]:
    latencies = [item.latency_ms for item in results]
    return {
        "recall_at_k": statistics.fmean(item.metrics.recall_at_k for item in results),
        "mrr_at_k": statistics.fmean(item.metrics.reciprocal_rank for item in results),
        "ndcg_at_k": statistics.fmean(item.metrics.ndcg_at_k for item in results),
        "context_precision_at_k": statistics.fmean(
            item.metrics.context_precision_at_k for item in results
        ),
        "latency_p50_ms": _percentile(latencies, 0.5),
        "latency_p95_ms": _percentile(latencies, 0.95),
    }


def _slice_metrics(
    results: Sequence[ExperimentCaseResult],
) -> tuple[SliceMetric, ...]:
    slices: dict[tuple[str, str], list[ExperimentCaseResult]] = defaultdict(list)
    for result in results:
        slices[("query_profile", result.query_profile)].append(result)
        for dimension, raw_value in result.taxonomy.items():
            values = raw_value if isinstance(raw_value, list) else [raw_value]
            for value in values:
                slices[(dimension, str(value))].append(result)
    output = []
    for (dimension, value), items in sorted(slices.items()):
        metrics = _aggregate(items)
        for metric_name in (
            "recall_at_k",
            "mrr_at_k",
            "ndcg_at_k",
            "context_precision_at_k",
            "latency_p50_ms",
            "latency_p95_ms",
        ):
            output.append(
                SliceMetric(
                    dimension=dimension,
                    value=value,
                    metric_name=metric_name,
                    metric_value=metrics[metric_name],
                    sample_size=len(items),
                )
            )
    return tuple(output)


def _blocked(
    manifest: ExperimentManifest,
    started_at: datetime,
    reason: str,
    *,
    document_count: int,
    eligible_case_count: int,
) -> ExperimentResult:
    return ExperimentResult(
        manifest=manifest,
        status=ExperimentStatus.BLOCKED,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        block_reason=reason,
        document_count=document_count,
        eligible_case_count=eligible_case_count,
    )


def _percentile(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = (len(ordered) - 1) * quantile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _chunk_cache_key(
    manifest: ExperimentManifest, documents: Sequence[EvaluationDocument]
) -> str:
    digest = hashlib.sha256()
    digest.update(manifest.chunker.model_dump_json().encode("utf-8"))
    for document in documents:
        digest.update(document.document_ref.encode("utf-8"))
        digest.update(hashlib.sha256(document.text.encode("utf-8")).digest())
    return digest.hexdigest()
