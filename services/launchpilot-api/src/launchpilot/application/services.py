from __future__ import annotations

from uuid import UUID

from launchpilot.domain.errors import NotFoundError
from launchpilot.domain.models import Campaign, CampaignObservation, Conversation

from .ports import CampaignRepository, ConversationRepository, ObservationRepository


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


class ObservationService:
    def __init__(
        self, campaigns: CampaignRepository, observations: ObservationRepository
    ) -> None:
        self._campaigns = campaigns
        self._observations = observations

    def record(self, observation: CampaignObservation) -> CampaignObservation:
        if self._campaigns.get(observation.campaign_id) is None:
            raise NotFoundError("campaign not found")
        self._observations.add(observation)
        return observation

    def list_for_campaign(self, campaign_id: UUID) -> list[CampaignObservation]:
        if self._campaigns.get(campaign_id) is None:
            raise NotFoundError("campaign not found")
        return self._observations.list_by_campaign(campaign_id)
