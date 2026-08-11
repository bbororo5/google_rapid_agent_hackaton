from __future__ import annotations

from typing import Protocol
from uuid import UUID

from launchpilot.performance.contracts import (
    CampaignMetricRequest,
    ConnectorFetchResult,
    ExternalAccount,
    ExternalCampaign,
    PlatformProvider,
)
from launchpilot.performance.models import CampaignObservation


class AdsConnector(Protocol):
    """Platform boundary for deterministic advertising-data collection."""

    @property
    def provider(self) -> PlatformProvider: ...

    def list_accounts(self, *, access_token: str) -> tuple[ExternalAccount, ...]: ...

    def list_campaigns(
        self, *, access_token: str, account_ref: str
    ) -> tuple[ExternalCampaign, ...]: ...

    def fetch_campaign_metrics(
        self, *, access_token: str, request: CampaignMetricRequest
    ) -> ConnectorFetchResult: ...


class ObservationRepository(Protocol):
    def add(self, observation: CampaignObservation) -> None: ...
    def list_by_campaign(self, campaign_id: UUID) -> list[CampaignObservation]: ...
