from uuid import UUID

from launchpilot.campaigns.public import CampaignService
from launchpilot.performance.models import CampaignObservation

from .ports import ObservationRepository


class ObservationService:
    def __init__(
        self, campaigns: CampaignService, observations: ObservationRepository
    ) -> None:
        self._campaigns = campaigns
        self._observations = observations

    def record(self, observation: CampaignObservation) -> CampaignObservation:
        self._campaigns.get(observation.campaign_id)
        self._observations.add(observation)
        return observation

    def list_for_campaign(self, campaign_id: UUID) -> list[CampaignObservation]:
        self._campaigns.get(campaign_id)
        return self._observations.list_by_campaign(campaign_id)
