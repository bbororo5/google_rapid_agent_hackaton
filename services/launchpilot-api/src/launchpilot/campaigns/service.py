from uuid import UUID

from launchpilot.shared import NotFoundError

from .models import Campaign, Conversation
from .ports import CampaignRepository, ConversationRepository


class CampaignService:
    def __init__(self, campaigns: CampaignRepository) -> None:
        self._campaigns = campaigns

    def create(self, campaign: Campaign) -> Campaign:
        self._campaigns.add(campaign)
        return campaign

    def get(self, campaign_id: UUID) -> Campaign:
        campaign = self._campaigns.get(campaign_id)
        if campaign is None:
            raise NotFoundError("campaign not found")
        return campaign

    def list(self) -> list[Campaign]:
        return self._campaigns.list()

    def list_for_workspaces(self, workspace_ids: set[UUID]) -> list[Campaign]:
        return self._campaigns.list_by_workspaces(workspace_ids)

    def require_campaign(self, campaign_id: UUID) -> None:
        self.get(campaign_id)


class ConversationService:
    def __init__(
        self, campaigns: CampaignRepository, conversations: ConversationRepository
    ) -> None:
        self._campaigns = campaigns
        self._conversations = conversations

    def create(self, conversation: Conversation) -> Conversation:
        if self._campaigns.get(conversation.campaign_id) is None:
            raise NotFoundError("campaign not found")
        self._conversations.add(conversation)
        return conversation

    def list_for_campaign(self, campaign_id: UUID) -> list[Conversation]:
        if self._campaigns.get(campaign_id) is None:
            raise NotFoundError("campaign not found")
        return self._conversations.list_by_campaign(campaign_id)
