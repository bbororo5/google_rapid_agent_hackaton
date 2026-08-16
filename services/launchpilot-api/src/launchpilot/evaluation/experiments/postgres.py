from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from psycopg.types.json import Jsonb

from launchpilot.persistence.postgres import PostgresDatabase

from .contracts import ExperimentResult


class PostgresExperimentResultRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def save(self, result: ExperimentResult) -> None:
        manifest = result.manifest
        with self._database.connect() as connection:
            connection.execute(
                """INSERT INTO retrieval_experiment_runs(
                    id, execution_id, matrix_version, golden_version, corpus_version, split,
                    chunker_method, chunker_version, chunker_config,
                    retriever_method, retriever_version, retriever_config,
                    status, block_reason, document_count, chunk_count,
                    eligible_case_count, aggregate_metrics, started_at, finished_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT(id) DO UPDATE SET
                    status = EXCLUDED.status,
                    block_reason = EXCLUDED.block_reason,
                    document_count = EXCLUDED.document_count,
                    chunk_count = EXCLUDED.chunk_count,
                    eligible_case_count = EXCLUDED.eligible_case_count,
                    aggregate_metrics = EXCLUDED.aggregate_metrics,
                    finished_at = EXCLUDED.finished_at""",
                (
                    manifest.experiment_id,
                    manifest.execution_id,
                    manifest.matrix_version,
                    manifest.golden_version,
                    manifest.corpus_version,
                    manifest.split,
                    manifest.chunker.method.value,
                    manifest.chunker.version,
                    Jsonb(manifest.chunker.model_dump(mode="json")),
                    manifest.retriever.method.value,
                    manifest.retriever.version,
                    Jsonb(manifest.retriever.model_dump(mode="json")),
                    result.status.value,
                    result.block_reason,
                    result.document_count,
                    result.chunk_count,
                    result.eligible_case_count,
                    Jsonb(result.aggregate_metrics),
                    result.started_at,
                    result.finished_at,
                ),
            )
            connection.execute(
                "DELETE FROM retrieval_experiment_case_results WHERE experiment_id = %s",
                (manifest.experiment_id,),
            )
            connection.execute(
                "DELETE FROM retrieval_experiment_slice_metrics WHERE experiment_id = %s",
                (manifest.experiment_id,),
            )
            if result.case_results:
                connection.cursor().executemany(
                    """INSERT INTO retrieval_experiment_case_results(
                        experiment_id, case_id, query_profile, taxonomy,
                        latency_ms, retrieved, metrics
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    [
                        (
                            manifest.experiment_id,
                            item.case_id,
                            item.query_profile,
                            Jsonb(item.taxonomy),
                            item.latency_ms,
                            Jsonb([_compact_hit(hit) for hit in item.retrieved]),
                            Jsonb(item.metrics.model_dump(mode="json")),
                        )
                        for item in result.case_results
                    ],
                )
            if result.slice_metrics:
                connection.cursor().executemany(
                    """INSERT INTO retrieval_experiment_slice_metrics(
                        experiment_id, dimension, value, metric_name,
                        metric_value, sample_size
                    ) VALUES (%s, %s, %s, %s, %s, %s)""",
                    [
                        (
                            manifest.experiment_id,
                            item.dimension,
                            item.value,
                            item.metric_name,
                            item.metric_value,
                            item.sample_size,
                        )
                        for item in result.slice_metrics
                    ],
                )

    def matrix_summary(
        self,
        matrix_version: str,
        *,
        execution_id: str | None = None,
    ) -> tuple[dict[str, Any], ...]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """SELECT id, execution_id, split, chunker_method, chunker_version,
                    retriever_method, retriever_version, status, block_reason,
                    document_count, chunk_count, eligible_case_count,
                    aggregate_metrics, started_at, finished_at
                FROM retrieval_experiment_runs
                WHERE matrix_version = %s
                  AND (%s::uuid IS NULL OR execution_id = %s::uuid)
                ORDER BY split, chunker_version, retriever_version""",
                (matrix_version, execution_id, execution_id),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def best_runs(
        self,
        *,
        matrix_version: str,
        metric_name: str,
        split: str = "tune",
        limit: int = 10,
        execution_id: str | None = None,
    ) -> tuple[dict[str, Any], ...]:
        if not metric_name.replace("_", "").isalnum():
            raise ValueError("metric_name contains invalid characters")
        with self._database.connect() as connection:
            rows = connection.execute(
                """SELECT id, execution_id, chunker_method, chunker_version,
                    retriever_method, retriever_version,
                    (aggregate_metrics ->> %s)::double precision AS metric_value,
                    (aggregate_metrics ->> 'latency_p95_ms')::double precision
                        AS latency_p95_ms
                FROM retrieval_experiment_runs
                WHERE matrix_version = %s AND split = %s AND status = 'completed'
                  AND aggregate_metrics ? %s
                  AND (%s::uuid IS NULL OR execution_id = %s::uuid)
                ORDER BY metric_value DESC, latency_p95_ms ASC
                LIMIT %s""",
                (
                    metric_name,
                    matrix_version,
                    split,
                    metric_name,
                    execution_id,
                    execution_id,
                    limit,
                ),
            ).fetchall()
        return tuple(dict(row) for row in rows)


def save_results(
    repository: PostgresExperimentResultRepository,
    results: Sequence[ExperimentResult],
) -> None:
    for result in results:
        repository.save(result)


def _compact_hit(hit: Any) -> dict[str, Any]:
    return {
        "chunk_id": hit.chunk.chunk_id,
        "document_ref": hit.chunk.document_ref,
        "char_start": hit.chunk.char_start,
        "char_end": hit.chunk.char_end,
        "score": hit.score,
        "rank": hit.rank,
        "component_scores": hit.component_scores,
    }
