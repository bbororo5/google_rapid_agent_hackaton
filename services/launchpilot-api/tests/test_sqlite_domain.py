from datetime import date
from uuid import uuid4

from launchpilot.domain.models import (
    Campaign,
    CampaignResourceBinding,
    Conversation,
    DateRange,
)
from launchpilot.infrastructure.sqlite_domain import (
    SqliteCampaignRepository,
    SqliteConversationRepository,
    SqliteDomainDatabase,
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
