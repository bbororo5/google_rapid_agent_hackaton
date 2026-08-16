from __future__ import annotations

import argparse
import json
import os
from collections.abc import Iterable
from pathlib import Path

from launchpilot.persistence.postgres import PostgresDatabase

from .local_adapters import (
    KoreanTfidfSparseEncoder,
    MarketingCrossFeatureReranker,
    MarketingDenseEncoder,
)
from .matrix import expand_matrix, load_matrix, write_result_bundle
from .postgres import PostgresExperimentResultRepository, save_results
from .retrievers import RetrieverFactory
from .runner import RetrievalExperimentRunner, load_golden_document_benchmark


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a versioned Chunker x Retriever Golden Dataset matrix."
    )
    parser.add_argument(
        "--matrix",
        type=Path,
        default=Path("evals/experiments/retrieval-matrix-v1.yaml"),
    )
    parser.add_argument(
        "--golden-root",
        type=Path,
        default=Path("evals/golden/golden-v1"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/runs/retrieval-matrix-v1"),
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="Optional PostgreSQL URL. When set, run and slice results are persisted.",
    )
    parser.add_argument(
        "--require-completed",
        action="store_true",
        help="Return a failing exit code when every combination is blocked.",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    documents, cases, golden_manifest = load_golden_document_benchmark(args.golden_root)
    matrix = load_matrix(args.matrix)
    manifests = expand_matrix(
        matrix,
        golden_version=str(golden_manifest["golden_version"]),
        corpus_version=str(golden_manifest["corpus_version"]),
    )
    runner = RetrievalExperimentRunner(
        RetrieverFactory(
            dense_encoder=MarketingDenseEncoder(),
            sparse_encoder=KoreanTfidfSparseEncoder(),
            reranker=MarketingCrossFeatureReranker(),
        )
    )
    results = tuple(runner.run(manifest, documents, cases) for manifest in manifests)
    run_root = write_result_bundle(args.output, results)
    if args.database_url:
        save_results(
            PostgresExperimentResultRepository(PostgresDatabase(args.database_url)),
            results,
        )
    completed = sum(result.status == "completed" for result in results)
    blocked = sum(result.status == "blocked" for result in results)
    selected_splits = set(matrix["splits"])
    selected_case_count = sum(case.split in selected_splits for case in cases)
    print(
        json.dumps(
            {
                "matrix_version": matrix["matrix_version"],
                "execution_id": str(manifests[0].execution_id) if manifests else None,
                "run_root": str(run_root),
                "documents": len(documents),
                "document_grounded_cases": len(cases),
                "selected_eligible_cases": selected_case_count,
                "combinations": len(results),
                "completed": completed,
                "blocked": blocked,
                "database_saved": bool(args.database_url),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if args.require_completed and completed == 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
