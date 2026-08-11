from __future__ import annotations

import os

import psycopg
import pytest
from elasticsearch import ApiError, ConnectionError, Elasticsearch

from launchpilot.persistence.postgres import PostgresDatabase

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://launchpilot:launchpilot-local@127.0.0.1:5432/launchpilot_test",
)
TEST_ELASTICSEARCH_URL = os.getenv("TEST_ELASTICSEARCH_URL", "http://127.0.0.1:9200")
TEST_ELASTICSEARCH_INDEX = "launchpilot-documents-test-v1"


def _truncate(database: PostgresDatabase) -> None:
    with database.connect() as connection:
        connection.execute(
            """TRUNCATE TABLE
                campaign_documents,
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


@pytest.fixture
def elasticsearch_test_index() -> tuple[str, str]:
    client = Elasticsearch(TEST_ELASTICSEARCH_URL, request_timeout=5)
    try:
        client.info()
    except (ApiError, ConnectionError) as error:
        pytest.fail(
            "Elasticsearch is unavailable. Run `docker compose up -d elasticsearch`."
            f" Original error: {error}"
        )
    client.indices.delete(index=TEST_ELASTICSEARCH_INDEX, ignore_unavailable=True)
    yield TEST_ELASTICSEARCH_URL, TEST_ELASTICSEARCH_INDEX
    client.indices.delete(index=TEST_ELASTICSEARCH_INDEX, ignore_unavailable=True)
