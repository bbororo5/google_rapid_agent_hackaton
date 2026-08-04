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
from launchpilot.infrastructure.sqlite_domain import (
    SqliteCampaignRepository,
    SqliteConversationRepository,
    SqliteDomainDatabase,
    SqliteObservationRepository,
)


def test_campaign_survives_repository_recreation(tmp_path) -> None:
    path = str(tmp_path / "domain.db")
    binding = CampaignResourceBinding(
        connection_id=uuid4(), resource_ref="campaigns/456", label="Launch"
    )
    campaign = Campaign.create(
        workspace_id=uuid4(),
        name="Persistent Campaign",
        goal="Survive process restart",
        period=DateRange(date(2026, 7, 1), date(2026, 7, 31)),
        target_metrics=("spend", "conversions"),
        resource_bindings=(binding,),
    )
    SqliteCampaignRepository(SqliteDomainDatabase(path)).add(campaign)

    restored = SqliteCampaignRepository(SqliteDomainDatabase(path)).get(campaign.id)

    assert restored == campaign


def test_conversation_survives_repository_recreation(tmp_path) -> None:
    path = str(tmp_path / "domain.db")
    database = SqliteDomainDatabase(path)
    campaigns = SqliteCampaignRepository(database)
    campaign = Campaign.create(
        workspace_id=uuid4(),
        name="Campaign",
        goal="Persist conversations",
        period=DateRange(date(2026, 7, 1), date(2026, 7, 31)),
    )
    campaigns.add(campaign)
    conversation = Conversation.create(campaign_id=campaign.id, title="Analysis")
    SqliteConversationRepository(database).add(conversation)

    restored = SqliteConversationRepository(
        SqliteDomainDatabase(path)
    ).list_by_campaign(campaign.id)

    assert restored == [conversation]


def test_campaign_list_filters_workspace_ownership(tmp_path) -> None:
    repository = SqliteCampaignRepository(
        SqliteDomainDatabase(str(tmp_path / "domain.db"))
    )
    allowed_workspace = uuid4()
    allowed = Campaign.create(
        workspace_id=allowed_workspace,
        name="Allowed",
        goal="Visible",
        period=DateRange(date(2026, 7, 1), date(2026, 7, 31)),
    )
    hidden = Campaign.create(
        workspace_id=uuid4(),
        name="Hidden",
        goal="Invisible",
        period=allowed.period,
    )
    repository.add(allowed)
    repository.add(hidden)

    assert repository.list_by_workspaces({allowed_workspace}) == [allowed]


def test_multiplatform_observation_survives_repository_recreation(tmp_path) -> None:
    path = str(tmp_path / "domain.db")
    database = SqliteDomainDatabase(path)
    campaigns = SqliteCampaignRepository(database)
    campaign = Campaign.create(
        workspace_id=uuid4(),
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
    SqliteObservationRepository(database).add(observation)

    restored = SqliteObservationRepository(SqliteDomainDatabase(path)).list_by_campaign(
        campaign.id
    )

    assert restored == [observation]
