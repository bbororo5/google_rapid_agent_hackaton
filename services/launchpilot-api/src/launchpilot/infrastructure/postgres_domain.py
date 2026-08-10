from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.types.json import Jsonb

from launchpilot.domain.models import (
    Campaign,
    CampaignObservation,
    CampaignResourceBinding,
    Completeness,
    CompletenessStatus,
    Conversation,
    DateRange,
    MetricObservation,
    PlatformSlice,
)

from .postgres_database import PostgresDatabase

Row = dict[str, Any]


def _campaign_from_row(row: Row) -> Campaign:
    resource_bindings = tuple(
        CampaignResourceBinding(
            connection_id=UUID(item["connection_id"]),
            resource_ref=item["resource_ref"],
            label=item.get("label"),
        )
        for item in row["resource_bindings"]
    )
    return Campaign(
        id=UUID(str(row["id"])),
        workspace_id=UUID(str(row["workspace_id"])),
        name=row["name"],
        goal=row["goal"],
        period=DateRange(start=row["period_start"], end=row["period_end"]),
        target_metrics=tuple(row["target_metrics"]),
        resource_bindings=resource_bindings,
        created_at=row["created_at"],
    )


class PostgresCampaignRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def add(self, campaign: Campaign) -> None:
        resource_bindings = [
            {
                "connection_id": str(item.connection_id),
                "resource_ref": item.resource_ref,
                "label": item.label,
            }
            for item in campaign.resource_bindings
        ]
        with self._database.connect() as connection:
            connection.execute(
                """INSERT INTO campaigns(
                    id, workspace_id, name, goal, period_start, period_end,
                    target_metrics, resource_bindings, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    campaign.id,
                    campaign.workspace_id,
                    campaign.name,
                    campaign.goal,
                    campaign.period.start,
                    campaign.period.end,
                    Jsonb(list(campaign.target_metrics)),
                    Jsonb(resource_bindings),
                    campaign.created_at,
                ),
            )

    def get(self, campaign_id: UUID) -> Campaign | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM campaigns WHERE id = %s", (campaign_id,)
            ).fetchone()
        return None if row is None else _campaign_from_row(row)

    def list(self) -> list[Campaign]:
        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM campaigns ORDER BY created_at"
            ).fetchall()
        return [_campaign_from_row(row) for row in rows]

    def list_by_workspaces(self, workspace_ids: set[UUID]) -> list[Campaign]:
        if not workspace_ids:
            return []
        with self._database.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM campaigns
                WHERE workspace_id = ANY(%s) ORDER BY created_at""",
                (list(workspace_ids),),
            ).fetchall()
        return [_campaign_from_row(row) for row in rows]


class PostgresConversationRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def add(self, conversation: Conversation) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """INSERT INTO conversations(id, campaign_id, title, created_at)
                VALUES (%s, %s, %s, %s)""",
                (
                    conversation.id,
                    conversation.campaign_id,
                    conversation.title,
                    conversation.created_at,
                ),
            )

    def list_by_campaign(self, campaign_id: UUID) -> list[Conversation]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """SELECT id, campaign_id, title, created_at FROM conversations
                WHERE campaign_id = %s ORDER BY created_at""",
                (campaign_id,),
            ).fetchall()
        return [
            Conversation(
                id=UUID(str(row["id"])),
                campaign_id=UUID(str(row["campaign_id"])),
                title=row["title"],
                created_at=row["created_at"],
            )
            for row in rows
        ]


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
