from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from launchpilot.devtools.synthetic_marketing import (
    SyntheticConfig,
    SyntheticPostgresSeeder,
    build_campaign_documents,
    build_campaign_plans,
    build_platform_days,
)
from launchpilot.persistence.postgres import PostgresDatabase


def test_campaign_plans_are_deterministic_and_cover_platforms() -> None:
    config = SyntheticConfig(
        workspaces=2,
        campaigns_per_workspace=6,
        days=30,
        start_date=date(2025, 1, 1),
        seed=17,
    )

    first = build_campaign_plans(config)
    second = build_campaign_plans(config)

    assert first == second
    assert len(first) == 12
    assert {platform for plan in first for platform in plan.platforms} == {
        "GOOGLE_ADS",
        "META_ADS",
        "YOUTUBE",
    }
    assert len({plan.id for plan in first}) == len(first)
    assert len({plan.name for plan in first}) == len(first)


def test_daily_metrics_are_mathematically_consistent() -> None:
    config = SyntheticConfig(workspaces=1, campaigns_per_workspace=1, days=30)
    campaign = build_campaign_plans(config)[0]

    platform_day = build_platform_days(
        campaign, day_index=5, total_days=config.days, seed=config.seed
    )[0]
    metrics = {metric.key: metric for metric in platform_day.metrics}

    assert metrics["ctr"].value == pytest.approx(
        metrics["clicks"].value / metrics["impressions"].value,
        abs=1e-8,
    )
    assert metrics["cvr"].value == pytest.approx(
        metrics["conversions"].value / metrics["clicks"].value,
        abs=1e-8,
    )
    assert metrics["roas"].value == pytest.approx(
        metrics["conversion_value"].value / metrics["spend"].value,
        abs=1e-8,
    )
    assert platform_day.connector.startswith("synthetic-")


def test_tracking_gap_is_explicit_and_omits_unsupported_metrics() -> None:
    config = SyntheticConfig(workspaces=1, campaigns_per_workspace=6, days=30)
    campaign = next(
        plan for plan in build_campaign_plans(config) if plan.pattern == "tracking_gap"
    )

    platform_day = build_platform_days(
        campaign,
        day_index=config.days // 2,
        total_days=config.days,
        seed=config.seed,
    )[0]
    metric_keys = {metric.key for metric in platform_day.metrics}

    assert platform_day.missing_reason is not None
    assert "conversions" not in metric_keys
    assert "roas" not in metric_keys
    assert platform_day.missing_reason.startswith("synthetic")


def test_campaign_documents_are_deterministic_and_span_ready() -> None:
    campaign = build_campaign_plans(
        SyntheticConfig(workspaces=1, campaigns_per_workspace=1, days=30)
    )[0]

    first = build_campaign_documents(campaign)
    second = build_campaign_documents(campaign)

    assert first == second
    assert {item.document_type for item in first} == {"BRIEF", "MEMO", "ANALYSIS"}
    assert all(len(item.content.split()) > 400 for item in first)
    assert "페이싱 원칙:" in first[0].content
    assert "핵심 관찰:" in first[1].content
    assert "권고 근거:" in first[2].content


def test_invalid_scale_is_rejected() -> None:
    with pytest.raises(ValueError, match="workspaces"):
        SyntheticConfig(workspaces=0)


def test_postgres_seed_replaces_only_the_synthetic_namespace(
    postgres_database: PostgresDatabase,
) -> None:
    real_workspace_id = uuid4()
    with postgres_database.connect() as connection:
        connection.execute(
            "INSERT INTO workspaces(id, name, created_at) VALUES (%s, %s, %s)",
            (real_workspace_id, "Real Workspace", datetime.now(UTC)),
        )

    seeder = SyntheticPostgresSeeder(postgres_database)
    seeder.seed(
        SyntheticConfig(workspaces=1, campaigns_per_workspace=2, days=2),
        show_progress=False,
    )
    summary = seeder.seed(
        SyntheticConfig(workspaces=1, campaigns_per_workspace=1, days=1),
        replace=True,
        show_progress=False,
    )

    with postgres_database.connect() as connection:
        real_workspace = connection.execute(
            "SELECT 1 FROM workspaces WHERE id = %s", (real_workspace_id,)
        ).fetchone()
        synthetic_campaigns = connection.execute(
            """SELECT count(*) AS total
            FROM campaigns c
            JOIN workspaces w ON w.id = c.workspace_id
            WHERE w.name LIKE 'Synthetic Marketing Lab %%'"""
        ).fetchone()
        synthetic_documents = connection.execute(
            "SELECT count(*) AS total FROM campaign_documents"
        ).fetchone()

    assert real_workspace is not None
    assert synthetic_campaigns is not None
    assert synthetic_campaigns["total"] == 1
    assert synthetic_documents["total"] == 3
    assert summary.campaigns == 1
    assert summary.observations == 1
    assert summary.documents == 3
