from __future__ import annotations

from typing import Any

from launchpilot.performance.retrieval import (
    CampaignMetricQuery,
    CampaignPerformance,
    CampaignSummary,
    MetricEvidence,
)
from launchpilot.persistence.postgres import PostgresDatabase


class PostgresStructuredRetrievalRepository:
    """Read model for exact campaign, period, platform, and metric retrieval."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def get_campaign_performance(
        self, query: CampaignMetricQuery
    ) -> CampaignPerformance | None:
        with self._database.connect() as connection:
            campaign_row = connection.execute(
                """SELECT id, name, goal, period_start, period_end, target_metrics
                FROM campaigns
                WHERE id = %s AND workspace_id = %s""",
                (query.campaign_id, query.workspace_id),
            ).fetchone()
            if campaign_row is None:
                return None

            clauses = ["o.campaign_id = %s"]
            parameters: list[Any] = [query.campaign_id]
            if query.start_date is not None and query.end_date is not None:
                clauses.extend(["o.period_start = %s", "o.period_end = %s"])
                parameters.extend([query.start_date, query.end_date])
            if query.platforms:
                clauses.append("s.surface = ANY(%s)")
                parameters.append([item.upper() for item in query.platforms])
            if query.metric_keys:
                clauses.append("m.metric_key = ANY(%s)")
                parameters.append(list(query.metric_keys))

            metric_rows = connection.execute(
                f"""WITH ranked_metrics AS (
                    SELECT
                        o.id AS observation_id,
                        o.captured_at,
                        o.completeness_status,
                        o.missing_reasons,
                        s.surface,
                        s.connector,
                        s.account_ref,
                        s.external_campaign_ref,
                        m.subject_ref,
                        m.subject_level,
                        m.metric_key,
                        m.value,
                        m.unit,
                        m.period_start,
                        m.period_end,
                        m.provenance_ref,
                        m.calculation,
                        row_number() OVER (
                            PARTITION BY
                                s.surface,
                                coalesce(s.external_campaign_ref, s.account_ref),
                                m.subject_ref,
                                m.metric_key,
                                m.period_start,
                                m.period_end
                            ORDER BY o.captured_at DESC, o.id DESC
                        ) AS freshness_rank
                    FROM campaign_observations o
                    JOIN platform_slices s ON s.observation_id = o.id
                    JOIN metric_observations m
                      ON m.observation_id = s.observation_id
                     AND m.slice_index = s.slice_index
                    WHERE {" AND ".join(clauses)}
                )
                SELECT * FROM ranked_metrics
                WHERE freshness_rank = 1
                ORDER BY surface, metric_key, subject_ref""",
                parameters,
            ).fetchall()

        return CampaignPerformance(
            campaign=CampaignSummary(
                id=campaign_row["id"],
                name=campaign_row["name"],
                goal=campaign_row["goal"],
                period_start=campaign_row["period_start"],
                period_end=campaign_row["period_end"],
                target_metrics=tuple(campaign_row["target_metrics"]),
            ),
            metrics=tuple(self._metric_from_row(row) for row in metric_rows),
        )

    @staticmethod
    def _metric_from_row(row: dict[str, Any]) -> MetricEvidence:
        return MetricEvidence(
            observation_id=row["observation_id"],
            captured_at=row["captured_at"],
            completeness_status=row["completeness_status"],
            missing_reasons=tuple(row["missing_reasons"]),
            surface=row["surface"],
            connector=row["connector"],
            account_ref=row["account_ref"],
            external_campaign_ref=row["external_campaign_ref"],
            subject_ref=row["subject_ref"],
            subject_level=row["subject_level"],
            metric_key=row["metric_key"],
            value=row["value"],
            unit=row["unit"],
            period_start=row["period_start"],
            period_end=row["period_end"],
            provenance_ref=row["provenance_ref"],
            calculation=row["calculation"],
        )
