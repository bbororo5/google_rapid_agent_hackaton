from uuid import UUID

from launchpilot.application.ports import CampaignRepository
from launchpilot.domain.errors import NotFoundError
from launchpilot.domain.models import CampaignObservation

from .ports import ObservationRepository


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
