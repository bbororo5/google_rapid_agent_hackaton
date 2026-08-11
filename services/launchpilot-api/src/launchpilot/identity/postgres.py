from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from cryptography.fernet import Fernet
from psycopg import Connection
from psycopg.types.json import Jsonb

from launchpilot.performance.contracts import (
    ExternalCampaignBinding,
    PlatformProvider,
)
from launchpilot.persistence.postgres import PostgresDatabase

from .models import ConnectedUser, PlatformConnection, WorkspaceAccess

Row = dict[str, Any]


def utc_now() -> datetime:
    return datetime.now(UTC)


class PostgresIdentityStore:
    """Persistent identity data with encrypted OAuth tokens."""

    def __init__(
        self, database: PostgresDatabase, token_encryption_key: str | None
    ) -> None:
        self._database = database
        self._cipher = (
            Fernet(token_encryption_key.encode()) if token_encryption_key else None
        )

    def upsert_user(
        self, *, google_subject: str, email: str, display_name: str | None
    ) -> ConnectedUser:
        with self._database.connect() as connection:
            row = connection.execute(
                """INSERT INTO users(
                    id, google_subject, email, display_name, created_at
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT(google_subject) DO UPDATE SET
                    email = excluded.email,
                    display_name = excluded.display_name
                RETURNING id""",
                (uuid4(), google_subject, email, display_name, utc_now()),
            ).fetchone()
            if row is None:
                raise RuntimeError("user upsert did not return an id")
            user_id = row["id"]
            self._ensure_personal_workspace(
                connection,
                user_id=user_id,
                workspace_name=f"{display_name or email} Workspace",
            )
        return ConnectedUser(str(user_id), google_subject, email, display_name)

    @staticmethod
    def _ensure_personal_workspace(
        connection: Connection[Row],
        *,
        user_id: UUID,
        workspace_name: str,
    ) -> None:
        membership = connection.execute(
            """SELECT workspace_id FROM workspace_memberships
            WHERE user_id = %s LIMIT 1""",
            (user_id,),
        ).fetchone()
        if membership is not None:
            return
        workspace_id = uuid4()
        now = utc_now()
        connection.execute(
            "INSERT INTO workspaces(id, name, created_at) VALUES (%s, %s, %s)",
            (workspace_id, workspace_name, now),
        )
        connection.execute(
            """INSERT INTO workspace_memberships(
                workspace_id, user_id, role, created_at
            ) VALUES (%s, %s, %s, %s)""",
            (workspace_id, user_id, "OWNER", now),
        )

    def get_user(self, user_id: str) -> ConnectedUser | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """SELECT id, google_subject, email, display_name
                FROM users WHERE id = %s""",
                (UUID(user_id),),
            ).fetchone()
        return (
            None
            if row is None
            else ConnectedUser(
                str(row["id"]),
                row["google_subject"],
                row["email"],
                row["display_name"],
            )
        )

    def list_workspaces(self, user_id: str) -> list[WorkspaceAccess]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """SELECT w.id, w.name, m.role
                FROM workspaces w
                JOIN workspace_memberships m ON m.workspace_id = w.id
                WHERE m.user_id = %s ORDER BY w.created_at""",
                (UUID(user_id),),
            ).fetchall()
        return [
            WorkspaceAccess(str(row["id"]), row["name"], row["role"]) for row in rows
        ]

    def has_workspace_access(self, *, user_id: str, workspace_id: str) -> bool:
        with self._database.connect() as connection:
            row = connection.execute(
                """SELECT 1 FROM workspace_memberships
                WHERE workspace_id = %s AND user_id = %s""",
                (UUID(workspace_id), UUID(user_id)),
            ).fetchone()
        return row is not None

    def upsert_connection(
        self,
        *,
        user_id: str,
        provider: str,
        token: dict[str, object],
        granted_scopes: tuple[str, ...],
        account_ref: str | None = None,
    ) -> PlatformConnection:
        cipher = self._require_cipher()
        with self._database.connect() as connection:
            row = connection.execute(
                """SELECT id, account_ref, encrypted_token
                FROM platform_connections
                WHERE user_id = %s AND provider = %s FOR UPDATE""",
                (UUID(user_id), provider),
            ).fetchone()
            connection_id = row["id"] if row else uuid4()
            resolved_account = (
                account_ref
                if account_ref is not None
                else (row["account_ref"] if row else None)
            )
            prior_token = (
                json.loads(cipher.decrypt(row["encrypted_token"].encode()).decode())
                if row
                else {}
            )
            encrypted_token = cipher.encrypt(
                json.dumps({**prior_token, **token}).encode()
            ).decode()
            now = utc_now()
            connection.execute(
                """INSERT INTO platform_connections(
                    id, user_id, provider, account_ref, granted_scopes,
                    encrypted_token, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(user_id, provider) DO UPDATE SET
                    account_ref = excluded.account_ref,
                    granted_scopes = excluded.granted_scopes,
                    encrypted_token = excluded.encrypted_token,
                    updated_at = excluded.updated_at""",
                (
                    connection_id,
                    UUID(user_id),
                    provider,
                    resolved_account,
                    Jsonb(list(granted_scopes)),
                    encrypted_token,
                    now,
                    now,
                ),
            )
        return PlatformConnection(
            str(connection_id), user_id, provider, resolved_account, granted_scopes
        )

    def list_connections(self, user_id: str) -> list[PlatformConnection]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """SELECT id, user_id, provider, account_ref, granted_scopes
                FROM platform_connections WHERE user_id = %s""",
                (UUID(user_id),),
            ).fetchall()
        return [
            PlatformConnection(
                str(row["id"]),
                str(row["user_id"]),
                row["provider"],
                row["account_ref"],
                tuple(row["granted_scopes"]),
            )
            for row in rows
        ]

    def get_connection_token(
        self, *, connection_id: str, user_id: str
    ) -> tuple[PlatformConnection, dict[str, object]] | None:
        cipher = self._require_cipher()
        with self._database.connect() as connection:
            row = connection.execute(
                """SELECT id, user_id, provider, account_ref,
                    granted_scopes, encrypted_token
                FROM platform_connections WHERE id = %s AND user_id = %s""",
                (UUID(connection_id), UUID(user_id)),
            ).fetchone()
        if row is None:
            return None
        platform_connection = PlatformConnection(
            str(row["id"]),
            str(row["user_id"]),
            row["provider"],
            row["account_ref"],
            tuple(row["granted_scopes"]),
        )
        return platform_connection, json.loads(
            cipher.decrypt(row["encrypted_token"].encode()).decode()
        )

    def upsert_campaign_binding(
        self,
        *,
        user_id: str,
        campaign_id: str,
        connection_id: str,
        external_account_ref: str,
        external_campaign_ref: str,
        display_name: str,
        currency_code: str | None = None,
        timezone: str | None = None,
        attribution_setting: str | None = None,
    ) -> ExternalCampaignBinding | None:
        with self._database.connect() as connection:
            platform_connection = connection.execute(
                """SELECT provider FROM platform_connections
                WHERE id = %s AND user_id = %s""",
                (UUID(connection_id), UUID(user_id)),
            ).fetchone()
            if platform_connection is None:
                return None
            existing = connection.execute(
                """SELECT id, created_at FROM external_campaign_bindings
                WHERE campaign_id = %s AND connection_id = %s
                  AND external_campaign_ref = %s""",
                (UUID(campaign_id), UUID(connection_id), external_campaign_ref),
            ).fetchone()
            binding = ExternalCampaignBinding(
                id=existing["id"] if existing else uuid4(),
                campaign_id=UUID(campaign_id),
                connection_id=connection_id,
                provider=PlatformProvider(platform_connection["provider"]),
                external_account_ref=external_account_ref,
                external_campaign_ref=external_campaign_ref,
                display_name=display_name,
                currency_code=currency_code,
                timezone=timezone,
                attribution_setting=attribution_setting,
                created_at=existing["created_at"] if existing else utc_now(),
            )
            connection.execute(
                """INSERT INTO external_campaign_bindings(
                    id, campaign_id, connection_id, provider, external_account_ref,
                    external_campaign_ref, display_name, currency_code, timezone,
                    attribution_setting, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(campaign_id, connection_id, external_campaign_ref)
                DO UPDATE SET
                    external_account_ref = excluded.external_account_ref,
                    display_name = excluded.display_name,
                    currency_code = excluded.currency_code,
                    timezone = excluded.timezone,
                    attribution_setting = excluded.attribution_setting""",
                (
                    binding.id,
                    binding.campaign_id,
                    UUID(binding.connection_id),
                    binding.provider.value,
                    binding.external_account_ref,
                    binding.external_campaign_ref,
                    binding.display_name,
                    binding.currency_code,
                    binding.timezone,
                    binding.attribution_setting,
                    binding.created_at,
                ),
            )
        return binding

    def list_campaign_bindings(
        self, *, user_id: str, campaign_id: str
    ) -> list[ExternalCampaignBinding]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """SELECT b.* FROM external_campaign_bindings b
                JOIN platform_connections p ON p.id = b.connection_id
                WHERE b.campaign_id = %s AND p.user_id = %s
                ORDER BY b.created_at""",
                (UUID(campaign_id), UUID(user_id)),
            ).fetchall()
        return [
            ExternalCampaignBinding(
                id=row["id"],
                campaign_id=row["campaign_id"],
                connection_id=str(row["connection_id"]),
                provider=PlatformProvider(row["provider"]),
                external_account_ref=row["external_account_ref"],
                external_campaign_ref=row["external_campaign_ref"],
                display_name=row["display_name"],
                currency_code=row["currency_code"],
                timezone=row["timezone"],
                attribution_setting=row["attribution_setting"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def _require_cipher(self) -> Fernet:
        if self._cipher is None:
            raise RuntimeError(
                "Token encryption is not configured. Set TOKEN_ENCRYPTION_KEY."
            )
        return self._cipher
