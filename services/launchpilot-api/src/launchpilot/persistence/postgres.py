from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

_MIGRATIONS = (
    (
        1,
        """
        CREATE TABLE users (
            id UUID PRIMARY KEY,
            google_subject TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL,
            display_name TEXT,
            created_at TIMESTAMPTZ NOT NULL
        );

        CREATE TABLE workspaces (
            id UUID PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        );

        CREATE TABLE workspace_memberships (
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY(workspace_id, user_id)
        );
        CREATE INDEX workspace_memberships_user_idx
            ON workspace_memberships(user_id);

        CREATE TABLE platform_connections (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider TEXT NOT NULL,
            account_ref TEXT,
            granted_scopes JSONB NOT NULL,
            encrypted_token TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            UNIQUE(user_id, provider)
        );

        CREATE TABLE campaigns (
            id UUID PRIMARY KEY,
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            goal TEXT NOT NULL,
            period_start DATE NOT NULL,
            period_end DATE NOT NULL,
            target_metrics JSONB NOT NULL,
            resource_bindings JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            CHECK (period_start <= period_end)
        );
        CREATE INDEX campaigns_workspace_created_idx
            ON campaigns(workspace_id, created_at);

        CREATE TABLE conversations (
            id UUID PRIMARY KEY,
            campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        );
        CREATE INDEX conversations_campaign_created_idx
            ON conversations(campaign_id, created_at);

        CREATE TABLE campaign_observations (
            id UUID PRIMARY KEY,
            campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            period_start DATE NOT NULL,
            period_end DATE NOT NULL,
            completeness_status TEXT NOT NULL,
            missing_reasons JSONB NOT NULL,
            captured_at TIMESTAMPTZ NOT NULL,
            CHECK (period_start <= period_end),
            CHECK (completeness_status IN ('COMPLETE', 'PARTIAL'))
        );
        CREATE INDEX observations_campaign_captured_idx
            ON campaign_observations(campaign_id, captured_at);

        CREATE TABLE platform_slices (
            observation_id UUID NOT NULL
                REFERENCES campaign_observations(id) ON DELETE CASCADE,
            slice_index INTEGER NOT NULL,
            surface TEXT NOT NULL,
            connector TEXT NOT NULL,
            account_ref TEXT NOT NULL,
            fetch_run_ref TEXT NOT NULL,
            external_campaign_ref TEXT,
            currency_code TEXT,
            timezone TEXT,
            attribution_setting TEXT,
            PRIMARY KEY(observation_id, slice_index)
        );

        CREATE TABLE metric_observations (
            observation_id UUID NOT NULL,
            slice_index INTEGER NOT NULL,
            metric_index INTEGER NOT NULL,
            subject_ref TEXT NOT NULL,
            subject_level TEXT NOT NULL,
            metric_key TEXT NOT NULL,
            value DOUBLE PRECISION NOT NULL,
            unit TEXT NOT NULL,
            period_start DATE NOT NULL,
            period_end DATE NOT NULL,
            provenance_ref TEXT NOT NULL,
            calculation TEXT,
            PRIMARY KEY(observation_id, slice_index, metric_index),
            FOREIGN KEY(observation_id, slice_index)
                REFERENCES platform_slices(observation_id, slice_index)
                ON DELETE CASCADE,
            CHECK (period_start <= period_end)
        );
        CREATE INDEX metrics_key_subject_idx
            ON metric_observations(metric_key, subject_ref);

        CREATE TABLE external_campaign_bindings (
            id UUID PRIMARY KEY,
            campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            connection_id UUID NOT NULL
                REFERENCES platform_connections(id) ON DELETE CASCADE,
            provider TEXT NOT NULL,
            external_account_ref TEXT NOT NULL,
            external_campaign_ref TEXT NOT NULL,
            display_name TEXT NOT NULL,
            currency_code TEXT,
            timezone TEXT,
            attribution_setting TEXT,
            created_at TIMESTAMPTZ NOT NULL,
            UNIQUE(campaign_id, connection_id, external_campaign_ref)
        );
        """,
    ),
    (
        2,
        """
        CREATE TABLE campaign_documents (
            id UUID PRIMARY KEY,
            campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            document_type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            source_ref TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            UNIQUE(campaign_id, source_ref),
            CHECK (document_type IN ('MEMO', 'BRIEF', 'ANALYSIS'))
        );
        CREATE INDEX campaign_documents_scope_created_idx
            ON campaign_documents(workspace_id, campaign_id, created_at);
        """,
    ),
    (
        3,
        """
        CREATE TABLE retrieval_experiment_runs (
            id UUID PRIMARY KEY,
            matrix_version TEXT NOT NULL,
            golden_version TEXT NOT NULL,
            corpus_version TEXT NOT NULL,
            split TEXT NOT NULL,
            chunker_method TEXT NOT NULL,
            chunker_version TEXT NOT NULL,
            chunker_config JSONB NOT NULL,
            retriever_method TEXT NOT NULL,
            retriever_version TEXT NOT NULL,
            retriever_config JSONB NOT NULL,
            status TEXT NOT NULL,
            block_reason TEXT,
            document_count INTEGER NOT NULL,
            chunk_count INTEGER NOT NULL,
            eligible_case_count INTEGER NOT NULL,
            aggregate_metrics JSONB NOT NULL,
            started_at TIMESTAMPTZ NOT NULL,
            finished_at TIMESTAMPTZ NOT NULL,
            CHECK (split IN ('tune', 'validation', 'holdout')),
            CHECK (status IN ('pending', 'running', 'completed', 'blocked', 'failed')),
            CHECK (document_count >= 0),
            CHECK (chunk_count >= 0),
            CHECK (eligible_case_count >= 0)
        );
        CREATE INDEX retrieval_experiment_runs_matrix_idx
            ON retrieval_experiment_runs(matrix_version, split, status);

        CREATE TABLE retrieval_experiment_case_results (
            experiment_id UUID NOT NULL
                REFERENCES retrieval_experiment_runs(id) ON DELETE CASCADE,
            case_id TEXT NOT NULL,
            query_profile TEXT NOT NULL,
            taxonomy JSONB NOT NULL,
            latency_ms DOUBLE PRECISION NOT NULL,
            retrieved JSONB NOT NULL,
            metrics JSONB NOT NULL,
            PRIMARY KEY(experiment_id, case_id),
            CHECK (latency_ms >= 0)
        );
        CREATE INDEX retrieval_experiment_cases_profile_idx
            ON retrieval_experiment_case_results(query_profile);

        CREATE TABLE retrieval_experiment_slice_metrics (
            experiment_id UUID NOT NULL
                REFERENCES retrieval_experiment_runs(id) ON DELETE CASCADE,
            dimension TEXT NOT NULL,
            value TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            metric_value DOUBLE PRECISION NOT NULL,
            sample_size INTEGER NOT NULL,
            PRIMARY KEY(experiment_id, dimension, value, metric_name),
            CHECK (sample_size > 0)
        );
        CREATE INDEX retrieval_experiment_slice_lookup_idx
            ON retrieval_experiment_slice_metrics(dimension, value, metric_name);
        """,
    ),
    (
        4,
        """
        ALTER TABLE retrieval_experiment_runs
            ADD COLUMN execution_id UUID;
        UPDATE retrieval_experiment_runs
            SET execution_id = id
            WHERE execution_id IS NULL;
        ALTER TABLE retrieval_experiment_runs
            ALTER COLUMN execution_id SET NOT NULL;
        CREATE INDEX retrieval_experiment_runs_execution_idx
            ON retrieval_experiment_runs(execution_id, split, status);
        """,
    ),
)


class PostgresDatabase:
    """Shared PostgreSQL connection boundary and minimal schema migrations."""

    def __init__(self, database_url: str) -> None:
        if not database_url.startswith(("postgresql://", "postgres://")):
            raise ValueError("DATABASE_URL must use PostgreSQL")
        self.database_url = database_url
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[Connection[dict[str, object]]]:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            yield connection

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext('launchpilot_schema_migrations'))"
            )
            applied = {
                row["version"]
                for row in connection.execute(
                    "SELECT version FROM schema_migrations"
                ).fetchall()
            }
            for version, sql in _MIGRATIONS:
                if version in applied:
                    continue
                connection.execute(sql)
                connection.execute(
                    "INSERT INTO schema_migrations(version) VALUES (%s)", (version,)
                )
