from __future__ import annotations

import os

import psycopg
import pytest

from launchpilot.infrastructure.postgres_database import PostgresDatabase

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://launchpilot:launchpilot-local@127.0.0.1:5432/launchpilot_test",
)


def _truncate(database: PostgresDatabase) -> None:
    with database.connect() as connection:
        connection.execute(
            """TRUNCATE TABLE
                external_campaign_bindings,
                metric_observations,
                platform_slices,
                campaign_observations,
                conversations,
                campaigns,
                platform_connections,
                workspace_memberships,
                workspaces,
                users
            CASCADE"""
        )


@pytest.fixture
def postgres_database() -> PostgresDatabase:
    try:
        database = PostgresDatabase(TEST_DATABASE_URL)
    except psycopg.OperationalError as error:
        pytest.fail(
            "PostgreSQL test database is unavailable. Run `docker compose up -d postgres`."
            f" Original error: {error}"
        )
    _truncate(database)
    yield database
    _truncate(database)
