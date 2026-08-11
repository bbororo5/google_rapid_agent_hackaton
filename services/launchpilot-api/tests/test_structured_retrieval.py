from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from launchpilot.domain.models import (
    Campaign,
    CampaignObservation,
    Completeness,
    CompletenessStatus,
    DateRange,
    MetricObservation,
    PlatformSlice,
)
from launchpilot.infrastructure.postgres_database import PostgresDatabase
from launchpilot.infrastructure.postgres_domain import (
    PostgresCampaignRepository,
)
from launchpilot.performance.observation_postgres import PostgresObservationRepository
from launchpilot.performance.postgres import (
    PostgresStructuredRetrievalRepository,
)
from launchpilot.performance.retrieval import CampaignMetricQuery


def test_retrieves_latest_exact_campaign_evidence(
    postgres_database: PostgresDatabase,
) -> None:
    workspace_id, campaign = _campaign(postgres_database)
    older = _observation(
        campaign, value=100, captured_at=datetime(2026, 8, 1, tzinfo=UTC)
    )
    latest = _observation(
        campaign, value=140, captured_at=datetime(2026, 8, 2, tzinfo=UTC)
    )
    observations = PostgresObservationRepository(postgres_database)
    observations.add(older)
    observations.add(latest)

    result = PostgresStructuredRetrievalRepository(
        postgres_database
    ).get_campaign_performance(
        CampaignMetricQuery(
            campaign_id=campaign.id,
            workspace_id=workspace_id,
            start_date=campaign.period.start,
            end_date=campaign.period.end,
            platforms=("google_ads",),
            metric_keys=("spend",),
        )
    )

    assert result is not None
    assert result.campaign.name == "Retrieval Campaign"
    assert len(result.metrics) == 1
    assert result.metrics[0].value == 140
    assert result.metrics[0].observation_id == latest.id
    assert result.metrics[0].provenance_ref == "google-ads:fetch-run"


def test_hides_campaign_from_other_workspace(
    postgres_database: PostgresDatabase,
) -> None:
    _, campaign = _campaign(postgres_database)

    result = PostgresStructuredRetrievalRepository(
        postgres_database
    ).get_campaign_performance(
        CampaignMetricQuery(campaign_id=campaign.id, workspace_id=uuid4())
    )

    assert result is None


def test_does_not_approximate_an_unstored_period(
    postgres_database: PostgresDatabase,
) -> None:
    workspace_id, campaign = _campaign(postgres_database)
    PostgresObservationRepository(postgres_database).add(
        _observation(campaign, value=100, captured_at=datetime.now(UTC))
    )

    result = PostgresStructuredRetrievalRepository(
        postgres_database
    ).get_campaign_performance(
        CampaignMetricQuery(
            campaign_id=campaign.id,
            workspace_id=workspace_id,
            start_date=campaign.period.start,
            end_date=campaign.period.end - timedelta(days=1),
        )
    )

    assert result is not None
    assert result.metrics == ()


def _campaign(database: PostgresDatabase):
    user_id = uuid4()
    workspace_id = uuid4()
    with database.connect() as connection:
        connection.execute(
            """INSERT INTO users(id, google_subject, email, created_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)""",
            (user_id, f"subject-{user_id}", f"{user_id}@example.com"),
        )
        connection.execute(
            """INSERT INTO workspaces(id, name, created_at)
            VALUES (%s, 'Retrieval Workspace', CURRENT_TIMESTAMP)""",
            (workspace_id,),
        )
        connection.execute(
            """INSERT INTO workspace_memberships(
                workspace_id, user_id, role, created_at
            ) VALUES (%s, %s, 'OWNER', CURRENT_TIMESTAMP)""",
            (workspace_id, user_id),
        )
    campaign = Campaign.create(
        workspace_id=workspace_id,
        name="Retrieval Campaign",
        goal="Retrieve exact evidence",
        period=DateRange(date(2026, 7, 1), date(2026, 7, 31)),
        target_metrics=("spend",),
    )
    PostgresCampaignRepository(database).add(campaign)
    return workspace_id, campaign


def _observation(
    campaign: Campaign, *, value: float, captured_at: datetime
) -> CampaignObservation:
    metric = MetricObservation(
        subject_ref="google-ads-campaign:1",
        subject_level="CAMPAIGN",
        metric_key="spend",
        value=value,
        unit="currency:KRW",
        period=campaign.period,
        provenance_ref="google-ads:fetch-run",
    )
    return CampaignObservation(
        id=uuid4(),
        campaign_id=campaign.id,
        period=campaign.period,
        platform_slices=(
            PlatformSlice(
                surface="GOOGLE_ADS",
                connector="google-ads-rest-v25",
                account_ref="customers/1",
                fetch_run_ref="fetch-run",
                external_campaign_ref="1",
                metrics=(metric,),
            ),
        ),
        completeness=Completeness(status=CompletenessStatus.COMPLETE),
        captured_at=captured_at,
    )
