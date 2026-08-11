from __future__ import annotations

from typing import Protocol
from uuid import UUID

from launchpilot.performance.models import CampaignObservation


class ObservationRepository(Protocol):
    def add(self, observation: CampaignObservation) -> None: ...
    def list_by_campaign(self, campaign_id: UUID) -> list[CampaignObservation]: ...


class CampaignExistenceVerifier(Protocol):
    def require_campaign(self, campaign_id: UUID) -> None: ...
