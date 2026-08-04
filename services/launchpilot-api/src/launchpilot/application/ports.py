from __future__ import annotations

from typing import Protocol
from uuid import UUID

from launchpilot.domain.integrations import (
    CampaignMetricRequest,
    ConnectorFetchResult,
    ExternalAccount,
    ExternalCampaign,
    PlatformProvider,
)
from launchpilot.domain.models import Campaign, CampaignObservation, Conversation


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


class CampaignRepository(Protocol):
    def add(self, campaign: Campaign) -> None: ...
    def get(self, campaign_id: UUID) -> Campaign | None: ...
    def list(self) -> list[Campaign]: ...
    def list_by_workspaces(self, workspace_ids: set[UUID]) -> list[Campaign]: ...


class ConversationRepository(Protocol):
    def add(self, conversation: Conversation) -> None: ...
    def list_by_campaign(self, campaign_id: UUID) -> list[Conversation]: ...


class ObservationRepository(Protocol):
    def add(self, observation: CampaignObservation) -> None: ...
    def list_by_campaign(self, campaign_id: UUID) -> list[CampaignObservation]: ...
