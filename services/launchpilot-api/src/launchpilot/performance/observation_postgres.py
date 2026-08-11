from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.types.json import Jsonb

from launchpilot.performance.models import (
    CampaignObservation,
    Completeness,
    CompletenessStatus,
    MetricObservation,
    PlatformSlice,
)
from launchpilot.persistence.postgres import PostgresDatabase
from launchpilot.shared import DateRange

Row = dict[str, Any]


class PostgresObservationRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def add(self, observation: CampaignObservation) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """INSERT INTO campaign_observations(
                    id, campaign_id, period_start, period_end, completeness_status,
                    missing_reasons, captured_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    observation.id,
                    observation.campaign_id,
                    observation.period.start,
                    observation.period.end,
                    observation.completeness.status.value,
                    Jsonb(list(observation.completeness.missing_reasons)),
                    observation.captured_at,
                ),
            )
            for slice_index, platform_slice in enumerate(observation.platform_slices):
                connection.execute(
                    """INSERT INTO platform_slices(
                        observation_id, slice_index, surface, connector, account_ref,
                        fetch_run_ref, external_campaign_ref, currency_code, timezone,
                        attribution_setting
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        observation.id,
                        slice_index,
                        str(platform_slice.surface),
                        platform_slice.connector,
                        platform_slice.account_ref,
                        platform_slice.fetch_run_ref,
                        platform_slice.external_campaign_ref,
                        platform_slice.currency_code,
                        platform_slice.timezone,
                        platform_slice.attribution_setting,
                    ),
                )
                for metric_index, metric in enumerate(platform_slice.metrics):
                    connection.execute(
                        """INSERT INTO metric_observations(
                            observation_id, slice_index, metric_index, subject_ref,
                            subject_level, metric_key, value, unit, period_start,
                            period_end, provenance_ref, calculation
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (
                            observation.id,
                            slice_index,
                            metric_index,
                            metric.subject_ref,
                            metric.subject_level,
                            metric.metric_key,
                            metric.value,
                            metric.unit,
                            metric.period.start,
                            metric.period.end,
                            metric.provenance_ref,
                            metric.calculation,
                        ),
                    )

    def list_by_campaign(self, campaign_id: UUID) -> list[CampaignObservation]:
        with self._database.connect() as connection:
            observation_rows = connection.execute(
                """SELECT * FROM campaign_observations
                WHERE campaign_id = %s ORDER BY captured_at""",
                (campaign_id,),
            ).fetchall()
            return [
                self._observation_from_row(connection, row) for row in observation_rows
            ]

    def _observation_from_row(
        self, connection: Connection[Row], row: Row
    ) -> CampaignObservation:
        slice_rows = connection.execute(
            """SELECT * FROM platform_slices
            WHERE observation_id = %s ORDER BY slice_index""",
            (row["id"],),
        ).fetchall()
        return CampaignObservation(
            id=UUID(str(row["id"])),
            campaign_id=UUID(str(row["campaign_id"])),
            period=DateRange(start=row["period_start"], end=row["period_end"]),
            platform_slices=tuple(
                self._slice_from_row(connection, slice_row) for slice_row in slice_rows
            ),
            completeness=Completeness(
                status=CompletenessStatus(row["completeness_status"]),
                missing_reasons=tuple(row["missing_reasons"]),
            ),
            captured_at=row["captured_at"],
        )

    @staticmethod
    def _slice_from_row(connection: Connection[Row], row: Row) -> PlatformSlice:
        metric_rows = connection.execute(
            """SELECT * FROM metric_observations
            WHERE observation_id = %s AND slice_index = %s ORDER BY metric_index""",
            (row["observation_id"], row["slice_index"]),
        ).fetchall()
        metrics = tuple(
            MetricObservation(
                subject_ref=metric["subject_ref"],
                subject_level=metric["subject_level"],
                metric_key=metric["metric_key"],
                value=metric["value"],
                unit=metric["unit"],
                period=DateRange(
                    start=metric["period_start"], end=metric["period_end"]
                ),
                provenance_ref=metric["provenance_ref"],
                calculation=metric["calculation"],
            )
            for metric in metric_rows
        )
        return PlatformSlice(
            surface=row["surface"],
            connector=row["connector"],
            account_ref=row["account_ref"],
            fetch_run_ref=row["fetch_run_ref"],
            metrics=metrics,
            external_campaign_ref=row["external_campaign_ref"],
            currency_code=row["currency_code"],
            timezone=row["timezone"],
            attribution_setting=row["attribution_setting"],
        )
