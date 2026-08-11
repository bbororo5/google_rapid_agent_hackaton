from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from launchpilot.campaigns.models import (
    Campaign,
    CampaignResourceBinding,
    Conversation,
)
from launchpilot.infrastructure.postgres_database import PostgresDatabase
from launchpilot.shared import DateRange

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
