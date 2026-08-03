from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from secrets import token_urlsafe
from uuid import uuid4

from cryptography.fernet import Fernet


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class OAuthTransaction:
    state: str
    purpose: str
    user_id: str | None
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ConnectedUser:
    id: str
    google_subject: str
    email: str
    display_name: str | None


@dataclass(frozen=True, slots=True)
class PlatformConnection:
    id: str
    user_id: str
    provider: str
    account_ref: str | None
    granted_scopes: tuple[str, ...]


class SqliteControlPlane:
    """Persistent control-plane data. OAuth tokens are encrypted before SQLite storage."""

    def __init__(self, database_path: str, token_encryption_key: str | None) -> None:
        self._database_path = database_path
        self._cipher = Fernet(token_encryption_key.encode()) if token_encryption_key else None
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    google_subject TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL,
                    display_name TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oauth_transactions (
                    state TEXT PRIMARY KEY,
                    purpose TEXT NOT NULL,
                    user_id TEXT,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS platform_connections (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    account_ref TEXT,
                    granted_scopes TEXT NOT NULL,
                    encrypted_token TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, provider)
                );
                """
            )

    def create_transaction(self, *, purpose: str, user_id: str | None) -> OAuthTransaction:
        transaction = OAuthTransaction(
            state=token_urlsafe(32),
            purpose=purpose,
            user_id=user_id,
            expires_at=utc_now() + timedelta(minutes=10),
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO oauth_transactions(state, purpose, user_id, expires_at) VALUES (?, ?, ?, ?)",
                (transaction.state, transaction.purpose, transaction.user_id, transaction.expires_at.isoformat()),
            )
        return transaction

    def consume_transaction(self, state: str, purpose: str) -> OAuthTransaction | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state, purpose, user_id, expires_at FROM oauth_transactions WHERE state = ?", (state,)
            ).fetchone()
            connection.execute("DELETE FROM oauth_transactions WHERE state = ?", (state,))
        if row is None or row["purpose"] != purpose:
            return None
        transaction = OAuthTransaction(
            state=row["state"], purpose=row["purpose"], user_id=row["user_id"], expires_at=datetime.fromisoformat(row["expires_at"])
        )
        return transaction if transaction.expires_at > utc_now() else None

    def upsert_user(self, *, google_subject: str, email: str, display_name: str | None) -> ConnectedUser:
        with self._connect() as connection:
            row = connection.execute("SELECT id FROM users WHERE google_subject = ?", (google_subject,)).fetchone()
            user_id = row["id"] if row else str(uuid4())
            connection.execute(
                """INSERT INTO users(id, google_subject, email, display_name, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(google_subject) DO UPDATE SET email=excluded.email, display_name=excluded.display_name""",
                (user_id, google_subject, email, display_name, utc_now().isoformat()),
            )
        return ConnectedUser(user_id, google_subject, email, display_name)

    def get_user(self, user_id: str) -> ConnectedUser | None:
        with self._connect() as connection:
            row = connection.execute("SELECT id, google_subject, email, display_name FROM users WHERE id = ?", (user_id,)).fetchone()
        return None if row is None else ConnectedUser(row["id"], row["google_subject"], row["email"], row["display_name"])

    def upsert_connection(
        self, *, user_id: str, provider: str, token: dict[str, object], granted_scopes: tuple[str, ...], account_ref: str | None = None
    ) -> PlatformConnection:
        if self._cipher is None:
            raise RuntimeError("Token encryption is not configured. Set TOKEN_ENCRYPTION_KEY.")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, account_ref, encrypted_token FROM platform_connections WHERE user_id = ? AND provider = ?", (user_id, provider)
            ).fetchone()
            connection_id = row["id"] if row else str(uuid4())
            resolved_account = account_ref if account_ref is not None else (row["account_ref"] if row else None)
            prior_token = json.loads(self._cipher.decrypt(row["encrypted_token"].encode()).decode()) if row else {}
            # Google usually returns a refresh token only on the first consent. Preserve it on reconnect.
            encrypted_token = self._cipher.encrypt(json.dumps({**prior_token, **token}).encode()).decode()
            now = utc_now().isoformat()
            connection.execute(
                """INSERT INTO platform_connections(id, user_id, provider, account_ref, granted_scopes, encrypted_token, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, provider) DO UPDATE SET
                  account_ref=excluded.account_ref, granted_scopes=excluded.granted_scopes,
                  encrypted_token=excluded.encrypted_token, updated_at=excluded.updated_at""",
                (connection_id, user_id, provider, resolved_account, json.dumps(granted_scopes), encrypted_token, now, now),
            )
        return PlatformConnection(connection_id, user_id, provider, resolved_account, granted_scopes)

    def list_connections(self, user_id: str) -> list[PlatformConnection]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, user_id, provider, account_ref, granted_scopes FROM platform_connections WHERE user_id = ?", (user_id,)
            ).fetchall()
        return [PlatformConnection(row["id"], row["user_id"], row["provider"], row["account_ref"], tuple(json.loads(row["granted_scopes"]))) for row in rows]

    def get_connection_token(self, *, connection_id: str, user_id: str) -> tuple[PlatformConnection, dict[str, object]] | None:
        if self._cipher is None:
            raise RuntimeError("Token encryption is not configured. Set TOKEN_ENCRYPTION_KEY.")
        with self._connect() as connection:
            row = connection.execute(
                """SELECT id, user_id, provider, account_ref, granted_scopes, encrypted_token
                FROM platform_connections WHERE id = ? AND user_id = ?""", (connection_id, user_id)
            ).fetchone()
        if row is None:
            return None
        connection = PlatformConnection(row["id"], row["user_id"], row["provider"], row["account_ref"], tuple(json.loads(row["granted_scopes"])))
        return connection, json.loads(self._cipher.decrypt(row["encrypted_token"].encode()).decode())
