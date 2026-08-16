from __future__ import annotations

import gzip
import json
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from .contracts import (
    ChunkingConfig,
    ExperimentManifest,
    ExperimentResult,
    ExperimentStatus,
    RetrievalConfig,
)


def load_matrix(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("experiment matrix root must be an object")
    for key in ("matrix_version", "splits", "chunkers", "retrievers"):
        if key not in payload:
            raise ValueError(f"experiment matrix is missing: {key}")
    return payload


def expand_matrix(
    payload: dict[str, Any],
    *,
    golden_version: str,
    corpus_version: str,
) -> tuple[ExperimentManifest, ...]:
    chunkers = [ChunkingConfig.model_validate(item) for item in payload["chunkers"]]
    retrievers = [
        RetrievalConfig.model_validate(item) for item in payload["retrievers"]
    ]
    execution_id = uuid4()
    return tuple(
        ExperimentManifest(
            execution_id=execution_id,
            matrix_version=str(payload["matrix_version"]),
            golden_version=golden_version,
            corpus_version=corpus_version,
            split=split,
            chunker=chunker,
            retriever=retriever,
        )
        for split in payload["splits"]
        for chunker in chunkers
        for retriever in retrievers
    )


def write_result_bundle(
    output_root: Path,
    results: Sequence[ExperimentResult],
) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    run_stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_root = output_root / run_stamp
    suffix = 1
    while run_root.exists():
        run_root = output_root / f"{run_stamp}-{suffix:02d}"
        suffix += 1
    run_root.mkdir(parents=True)
    with gzip.open(run_root / "results.jsonl.gz", "wt", encoding="utf-8") as output:
        for result in results:
            output.write(
                json.dumps(
                    result.model_dump(mode="json"),
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
    summary = _summary(results)
    (run_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (run_root / "report.md").write_text(_markdown_report(summary), encoding="utf-8")
    return run_root


def _summary(results: Sequence[ExperimentResult]) -> dict[str, Any]:
    statuses = Counter(result.status.value for result in results)
    block_reasons = Counter(
        result.block_reason
        for result in results
        if result.status == ExperimentStatus.BLOCKED and result.block_reason
    )
    completed = [
        _completed_summary(result)
        for result in results
        if result.status == ExperimentStatus.COMPLETED
    ]
    completed.sort(
        key=lambda item: (
            -float(item.get("ndcg_at_k", 0.0)),
            -float(item.get("query_profile_ndcg_floor", 0.0)),
            -float(item.get("recall_at_k", 0.0)),
            -float(item.get("context_precision_at_k", 0.0)),
            float(item.get("latency_p95_ms", 0.0)),
        )
    )
    return {
        "execution_id": (str(results[0].manifest.execution_id) if results else None),
        "matrix_version": results[0].manifest.matrix_version if results else None,
        "generated_at": datetime.now(UTC).isoformat(),
        "total_combinations": len(results),
        "status_distribution": dict(sorted(statuses.items())),
        "block_reasons": dict(sorted(block_reasons.items())),
        "completed_ranking": completed,
        "selection_policy": (
            "Use tune to shortlist, validation to select, and holdout once. "
            "Rank by nDCG@K and Recall@K subject to slice floors and latency/cost limits."
        ),
        "tune_shortlist_allowed": any(item["split"] == "tune" for item in completed),
        "validation_selection_allowed": any(
            item["split"] == "validation" for item in completed
        ),
        "holdout_confirmation_allowed": any(
            item["split"] == "holdout" for item in completed
        ),
    }


def _markdown_report(summary: dict[str, Any]) -> str:
    lines = [
        f"# Retrieval experiment report: {summary['matrix_version']}",
        "",
        f"- Execution ID: {summary['execution_id']}",
        f"- Total combinations: {summary['total_combinations']}",
        f"- Status: {summary['status_distribution']}",
        f"- Tune shortlist allowed: {summary['tune_shortlist_allowed']}",
        f"- Validation selection allowed: {summary['validation_selection_allowed']}",
        f"- Holdout confirmation allowed: {summary['holdout_confirmation_allowed']}",
        "",
    ]
    if summary["block_reasons"]:
        lines.extend(["## Blocked reasons", ""])
        lines.extend(
            f"- {reason}: {count} combinations"
            for reason, count in summary["block_reasons"].items()
        )
        lines.append("")
    ranking = summary["completed_ranking"]
    if ranking:
        lines.extend(
            [
                "## Completed ranking",
                "",
                "| Split | Chunker | Retriever | Recall@K | nDCG@K | Context P@K | Slice floor | p95 ms |",
                "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        lines.extend(
            "| {split} | {chunker} | {retriever} | {recall_at_k:.4f} | "
            "{ndcg_at_k:.4f} | {context_precision_at_k:.4f} | "
            "{query_profile_ndcg_floor:.4f} | "
            "{latency_p95_ms:.2f} |".format(**item)
            for item in ranking
        )
    else:
        lines.extend(
            [
                "## Interpretation",
                "",
                "No retrieval winner can be selected because no combination completed.",
                "Resolve the blocked prerequisites and rerun the same matrix.",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _completed_summary(result: ExperimentResult) -> dict[str, Any]:
    profile_metrics: dict[str, dict[str, float]] = {}
    for metric in result.slice_metrics:
        if metric.dimension != "query_profile":
            continue
        profile_metrics.setdefault(metric.value, {})[metric.metric_name] = (
            metric.metric_value
        )
    ndcg_values = [
        metrics["ndcg_at_k"]
        for metrics in profile_metrics.values()
        if "ndcg_at_k" in metrics
    ]
    return {
        "execution_id": str(result.manifest.execution_id),
        "experiment_id": str(result.manifest.experiment_id),
        "split": result.manifest.split,
        "chunker": result.manifest.chunker.version,
        "retriever": result.manifest.retriever.version,
        **result.aggregate_metrics,
        "query_profile_ndcg_floor": min(ndcg_values) if ndcg_values else 0.0,
        "query_profile_metrics": profile_metrics,
    }
