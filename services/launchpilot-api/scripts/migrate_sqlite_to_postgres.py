from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from psycopg.types.json import Jsonb

from launchpilot.infrastructure.postgres_database import PostgresDatabase

TABLES = (
    "users",
    "workspaces",
    "workspace_memberships",
    "platform_connections",
    "campaigns",
    "conversations",
    "campaign_observations",
    "platform_slices",
    "metric_observations",
    "external_campaign_bindings",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy the archived LaunchPilot SQLite data into empty PostgreSQL tables."
    )
    parser.add_argument("--sqlite-path", default="./data/launchpilot.db")
    parser.add_argument(
        "--database-url",
        default="postgresql://launchpilot:launchpilot-local@127.0.0.1:5432/launchpilot",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sqlite_path = Path(args.sqlite_path)
    if not sqlite_path.is_file():
        raise SystemExit(f"SQLite source does not exist: {sqlite_path}")

    source = sqlite3.connect(sqlite_path)
    source.row_factory = sqlite3.Row
    target = PostgresDatabase(args.database_url)

    with target.connect() as connection:
        populated = {
            table: connection.execute(
                f"SELECT count(*) AS count FROM {table}"
            ).fetchone()["count"]
            for table in TABLES
        }
        if any(populated.values()):
            raise SystemExit(
                "PostgreSQL target is not empty; migration stopped to avoid merging data."
            )

        counts = {
            "users": _copy_users(source, connection),
            "workspaces": _copy_workspaces(source, connection),
            "workspace_memberships": _copy_memberships(source, connection),
            "platform_connections": _copy_connections(source, connection),
            "campaigns": _copy_campaigns(source, connection),
            "conversations": _copy_conversations(source, connection),
            "campaign_observations": _copy_observations(source, connection),
            "platform_slices": _copy_slices(source, connection),
            "metric_observations": _copy_metrics(source, connection),
            "external_campaign_bindings": _copy_bindings(source, connection),
        }

    source.close()
    print("SQLite to PostgreSQL migration complete:")
    for table, count in counts.items():
        print(f"- {table}: {count}")


def _rows(source: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    exists = source.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return [] if exists is None else source.execute(f"SELECT * FROM {table}").fetchall()


def _copy_users(source, target) -> int:
    rows = _rows(source, "users")
    for row in rows:
        target.execute("INSERT INTO users VALUES (%s, %s, %s, %s, %s)", tuple(row))
    return len(rows)


def _copy_workspaces(source, target) -> int:
    rows = _rows(source, "workspaces")
    for row in rows:
        target.execute("INSERT INTO workspaces VALUES (%s, %s, %s)", tuple(row))
    return len(rows)


def _copy_memberships(source, target) -> int:
    rows = _rows(source, "workspace_memberships")
    for row in rows:
        target.execute(
            "INSERT INTO workspace_memberships VALUES (%s, %s, %s, %s)",
            tuple(row),
        )
    return len(rows)


def _copy_connections(source, target) -> int:
    rows = _rows(source, "platform_connections")
    for row in rows:
        values = list(row)
        values[4] = Jsonb(json.loads(values[4]))
        target.execute(
            """INSERT INTO platform_connections(
                id, user_id, provider, account_ref, granted_scopes,
                encrypted_token, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            values,
        )
    return len(rows)


def _copy_campaigns(source, target) -> int:
    rows = _rows(source, "campaigns")
    for row in rows:
        values = list(row)
        values[6] = Jsonb(json.loads(values[6]))
        values[7] = Jsonb(json.loads(values[7]))
        target.execute(
            """INSERT INTO campaigns(
                id, workspace_id, name, goal, period_start, period_end,
                target_metrics, resource_bindings, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            values,
        )
    return len(rows)


def _copy_conversations(source, target) -> int:
    rows = _rows(source, "conversations")
    for row in rows:
        target.execute("INSERT INTO conversations VALUES (%s, %s, %s, %s)", tuple(row))
    return len(rows)


def _copy_observations(source, target) -> int:
    rows = _rows(source, "campaign_observations")
    for row in rows:
        values = list(row)
        values[5] = Jsonb(json.loads(values[5]))
        target.execute(
            """INSERT INTO campaign_observations(
                id, campaign_id, period_start, period_end, completeness_status,
                missing_reasons, captured_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            values,
        )
    return len(rows)


def _copy_slices(source, target) -> int:
    rows = _rows(source, "platform_slices")
    for row in rows:
        target.execute(
            """INSERT INTO platform_slices(
                observation_id, slice_index, surface, connector, account_ref,
                fetch_run_ref, external_campaign_ref, currency_code, timezone,
                attribution_setting
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            tuple(row),
        )
    return len(rows)


def _copy_metrics(source, target) -> int:
    rows = _rows(source, "metric_observations")
    for row in rows:
        target.execute(
            """INSERT INTO metric_observations(
                observation_id, slice_index, metric_index, subject_ref,
                subject_level, metric_key, value, unit, period_start,
                period_end, provenance_ref, calculation
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            tuple(row),
        )
    return len(rows)


def _copy_bindings(source, target) -> int:
    rows = _rows(source, "external_campaign_bindings")
    for row in rows:
        target.execute(
            """INSERT INTO external_campaign_bindings(
                id, campaign_id, connection_id, provider, external_account_ref,
                external_campaign_ref, display_name, currency_code, timezone,
                attribution_setting, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            tuple(row),
        )
    return len(rows)


if __name__ == "__main__":
    main()
