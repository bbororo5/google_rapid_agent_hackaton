from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from uuid import UUID

from launchpilot.domain.models import (
    Campaign,
    CampaignResourceBinding,
    Conversation,
    DateRange,
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
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self.connect() as connection:
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
