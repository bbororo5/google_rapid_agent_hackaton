from datetime import date
from uuid import uuid4

from launchpilot.domain.models import (
    Campaign,
    CampaignObservation,
    CampaignResourceBinding,
    Completeness,
    CompletenessStatus,
    Conversation,
    DateRange,
    MetricObservation,
    PlatformSlice,
)
from launchpilot.infrastructure.postgres_database import PostgresDatabase
from launchpilot.infrastructure.postgres_domain import (
    PostgresCampaignRepository,
    PostgresConversationRepository,
    PostgresObservationRepository,
)


def test_campaign_survives_repository_recreation(
    postgres_database: PostgresDatabase,
) -> None:
    binding = CampaignResourceBinding(
        connection_id=uuid4(), resource_ref="campaigns/456", label="Launch"
    )
    workspace_id = _create_workspace(postgres_database)
    campaign = Campaign.create(
        workspace_id=workspace_id,
        name="Persistent Campaign",
        goal="Survive process restart",
        period=DateRange(date(2026, 7, 1), date(2026, 7, 31)),
        target_metrics=("spend", "conversions"),
        resource_bindings=(binding,),
    )
    PostgresCampaignRepository(postgres_database).add(campaign)

    recreated = PostgresDatabase(postgres_database.database_url)
    restored = PostgresCampaignRepository(recreated).get(campaign.id)

    assert restored == campaign


def test_conversation_survives_repository_recreation(
    postgres_database: PostgresDatabase,
) -> None:
    campaigns = PostgresCampaignRepository(postgres_database)
    campaign = Campaign.create(
        workspace_id=_create_workspace(postgres_database),
        name="Campaign",
        goal="Persist conversations",
        period=DateRange(date(2026, 7, 1), date(2026, 7, 31)),
    )
    campaigns.add(campaign)
    conversation = Conversation.create(campaign_id=campaign.id, title="Analysis")
    PostgresConversationRepository(postgres_database).add(conversation)

    recreated = PostgresDatabase(postgres_database.database_url)
    restored = PostgresConversationRepository(recreated).list_by_campaign(campaign.id)

    assert restored == [conversation]


def test_campaign_list_filters_workspace_ownership(
    postgres_database: PostgresDatabase,
) -> None:
    repository = PostgresCampaignRepository(postgres_database)
    allowed_workspace = _create_workspace(postgres_database)
    hidden_workspace = _create_workspace(postgres_database)
    allowed = Campaign.create(
        workspace_id=allowed_workspace,
        name="Allowed",
        goal="Visible",
        period=DateRange(date(2026, 7, 1), date(2026, 7, 31)),
    )
    hidden = Campaign.create(
        workspace_id=hidden_workspace,
        name="Hidden",
        goal="Invisible",
        period=allowed.period,
    )
    repository.add(allowed)
    repository.add(hidden)

    assert repository.list_by_workspaces({allowed_workspace}) == [allowed]


def test_multiplatform_observation_survives_repository_recreation(
    postgres_database: PostgresDatabase,
) -> None:
    campaigns = PostgresCampaignRepository(postgres_database)
    campaign = Campaign.create(
        workspace_id=_create_workspace(postgres_database),
        name="Persistent Observation",
        goal="Feed retrieval after restart",
        period=DateRange(date(2026, 7, 1), date(2026, 7, 31)),
    )
    campaigns.add(campaign)
    metric = MetricObservation(
        subject_ref="google-ads-campaign:456",
        subject_level="CAMPAIGN",
        metric_key="spend",
        value=12500.5,
        unit="currency:KRW",
        period=campaign.period,
        provenance_ref="google-ads:run-1",
        calculation="cost_micros / 1000000",
    )
    observation = CampaignObservation(
        id=uuid4(),
        campaign_id=campaign.id,
        period=campaign.period,
        platform_slices=(
            PlatformSlice(
                surface="GOOGLE_ADS",
                connector="google-ads-rest-v25",
                account_ref="customers/123",
                fetch_run_ref="run-1",
                metrics=(metric,),
                external_campaign_ref="456",
                currency_code="KRW",
                timezone="Asia/Seoul",
                attribution_setting="last-click",
            ),
        ),
        completeness=Completeness(
            status=CompletenessStatus.PARTIAL,
            missing_reasons=("META_ADS authorization expired",),
        ),
    )
    PostgresObservationRepository(postgres_database).add(observation)

    recreated = PostgresDatabase(postgres_database.database_url)
    restored = PostgresObservationRepository(recreated).list_by_campaign(campaign.id)

    assert restored == [observation]


def _create_workspace(database: PostgresDatabase):
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
            VALUES (%s, %s, CURRENT_TIMESTAMP)""",
            (workspace_id, "Test Workspace"),
        )
        connection.execute(
            """INSERT INTO workspace_memberships(
                workspace_id, user_id, role, created_at
            ) VALUES (%s, %s, 'OWNER', CURRENT_TIMESTAMP)""",
            (workspace_id, user_id),
        )
    return workspace_id
