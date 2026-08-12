from typing import Protocol
from uuid import UUID

from ..models import CampaignObservation


class ObservationRecorder(Protocol):
    """Stores a validated campaign performance snapshot."""

    def record(self, observation: CampaignObservation) -> CampaignObservation: ...


class ObservationCatalog(ObservationRecorder, Protocol):
    def list_for_campaign(self, campaign_id: UUID) -> list[CampaignObservation]: ...
