from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from uuid import UUID

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


class SqliteDomainDatabase:
    """Durable domain-data database shared by the SQLite repository adapters."""

    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS campaigns (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    target_metrics TEXT NOT NULL,
                    resource_bindings TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS campaigns_workspace_created_idx
                    ON campaigns(workspace_id, created_at);

                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    campaign_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS conversations_campaign_created_idx
                    ON conversations(campaign_id, created_at);

                CREATE TABLE IF NOT EXISTS campaign_observations (
                    id TEXT PRIMARY KEY,
                    campaign_id TEXT NOT NULL,
                    period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    completeness_status TEXT NOT NULL,
                    missing_reasons TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS observations_campaign_captured_idx
                    ON campaign_observations(campaign_id, captured_at);

                CREATE TABLE IF NOT EXISTS platform_slices (
                    observation_id TEXT NOT NULL,
                    slice_index INTEGER NOT NULL,
                    surface TEXT NOT NULL,
                    connector TEXT NOT NULL,
                    account_ref TEXT NOT NULL,
                    fetch_run_ref TEXT NOT NULL,
                    external_campaign_ref TEXT,
                    currency_code TEXT,
                    timezone TEXT,
                    attribution_setting TEXT,
                    PRIMARY KEY(observation_id, slice_index),
                    FOREIGN KEY(observation_id) REFERENCES campaign_observations(id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS metric_observations (
                    observation_id TEXT NOT NULL,
                    slice_index INTEGER NOT NULL,
                    metric_index INTEGER NOT NULL,
                    subject_ref TEXT NOT NULL,
                    subject_level TEXT NOT NULL,
                    metric_key TEXT NOT NULL,
                    value REAL NOT NULL,
                    unit TEXT NOT NULL,
                    period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    provenance_ref TEXT NOT NULL,
                    calculation TEXT,
                    PRIMARY KEY(observation_id, slice_index, metric_index),
                    FOREIGN KEY(observation_id, slice_index)
                        REFERENCES platform_slices(observation_id, slice_index)
                        ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS metrics_key_subject_idx
                    ON metric_observations(metric_key, subject_ref);
                """
            )


def _campaign_from_row(row: sqlite3.Row) -> Campaign:
    resource_bindings = tuple(
        CampaignResourceBinding(
            connection_id=UUID(item["connection_id"]),
            resource_ref=item["resource_ref"],
            label=item.get("label"),
        )
        for item in json.loads(row["resource_bindings"])
    )
    return Campaign(
        id=UUID(row["id"]),
        workspace_id=UUID(row["workspace_id"]),
        name=row["name"],
        goal=row["goal"],
        period=DateRange(
            start=date.fromisoformat(row["period_start"]),
            end=date.fromisoformat(row["period_end"]),
        ),
        target_metrics=tuple(json.loads(row["target_metrics"])),
        resource_bindings=resource_bindings,
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class SqliteCampaignRepository:
    def __init__(self, database: SqliteDomainDatabase) -> None:
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
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(campaign.id),
                    str(campaign.workspace_id),
                    campaign.name,
                    campaign.goal,
                    campaign.period.start.isoformat(),
                    campaign.period.end.isoformat(),
                    json.dumps(campaign.target_metrics),
                    json.dumps(resource_bindings),
                    campaign.created_at.isoformat(),
                ),
            )

    def get(self, campaign_id: UUID) -> Campaign | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM campaigns WHERE id = ?", (str(campaign_id),)
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
        placeholders = ",".join("?" for _ in workspace_ids)
        with self._database.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM campaigns WHERE workspace_id IN ({placeholders}) ORDER BY created_at",
                tuple(str(item) for item in workspace_ids),
            ).fetchall()
        return [_campaign_from_row(row) for row in rows]


class SqliteConversationRepository:
    def __init__(self, database: SqliteDomainDatabase) -> None:
        self._database = database

    def add(self, conversation: Conversation) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """INSERT INTO conversations(id, campaign_id, title, created_at)
                VALUES (?, ?, ?, ?)""",
                (
                    str(conversation.id),
                    str(conversation.campaign_id),
                    conversation.title,
                    conversation.created_at.isoformat(),
                ),
            )

    def list_by_campaign(self, campaign_id: UUID) -> list[Conversation]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """SELECT id, campaign_id, title, created_at FROM conversations
                WHERE campaign_id = ? ORDER BY created_at""",
                (str(campaign_id),),
            ).fetchall()
        return [
            Conversation(
                id=UUID(row["id"]),
                campaign_id=UUID(row["campaign_id"]),
                title=row["title"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]


class SqliteObservationRepository:
    def __init__(self, database: SqliteDomainDatabase) -> None:
        self._database = database

    def add(self, observation: CampaignObservation) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """INSERT INTO campaign_observations(
                    id, campaign_id, period_start, period_end, completeness_status,
                    missing_reasons, captured_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(observation.id),
                    str(observation.campaign_id),
                    observation.period.start.isoformat(),
                    observation.period.end.isoformat(),
                    observation.completeness.status,
                    json.dumps(observation.completeness.missing_reasons),
                    observation.captured_at.isoformat(),
                ),
            )
            for slice_index, platform_slice in enumerate(observation.platform_slices):
                connection.execute(
                    """INSERT INTO platform_slices(
                        observation_id, slice_index, surface, connector, account_ref,
                        fetch_run_ref, external_campaign_ref, currency_code, timezone,
                        attribution_setting
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(observation.id),
                        slice_index,
                        platform_slice.surface,
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
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            str(observation.id),
                            slice_index,
                            metric_index,
                            metric.subject_ref,
                            metric.subject_level,
                            metric.metric_key,
                            metric.value,
                            metric.unit,
                            metric.period.start.isoformat(),
                            metric.period.end.isoformat(),
                            metric.provenance_ref,
                            metric.calculation,
                        ),
                    )

    def list_by_campaign(self, campaign_id: UUID) -> list[CampaignObservation]:
        with self._database.connect() as connection:
            observation_rows = connection.execute(
                """SELECT * FROM campaign_observations
                WHERE campaign_id = ? ORDER BY captured_at""",
                (str(campaign_id),),
            ).fetchall()
            observations = [
                self._observation_from_row(connection, row) for row in observation_rows
            ]
        return observations

    def _observation_from_row(
        self, connection: sqlite3.Connection, row: sqlite3.Row
    ) -> CampaignObservation:
        slice_rows = connection.execute(
            """SELECT * FROM platform_slices
            WHERE observation_id = ? ORDER BY slice_index""",
            (row["id"],),
        ).fetchall()
        platform_slices = tuple(
            self._slice_from_row(connection, slice_row) for slice_row in slice_rows
        )
        return CampaignObservation(
            id=UUID(row["id"]),
            campaign_id=UUID(row["campaign_id"]),
            period=DateRange(
                start=date.fromisoformat(row["period_start"]),
                end=date.fromisoformat(row["period_end"]),
            ),
            platform_slices=platform_slices,
            completeness=Completeness(
                status=CompletenessStatus(row["completeness_status"]),
                missing_reasons=tuple(json.loads(row["missing_reasons"])),
            ),
            captured_at=datetime.fromisoformat(row["captured_at"]),
        )

    @staticmethod
    def _slice_from_row(
        connection: sqlite3.Connection, row: sqlite3.Row
    ) -> PlatformSlice:
        metric_rows = connection.execute(
            """SELECT * FROM metric_observations
            WHERE observation_id = ? AND slice_index = ? ORDER BY metric_index""",
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
                    start=date.fromisoformat(metric["period_start"]),
                    end=date.fromisoformat(metric["period_end"]),
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
