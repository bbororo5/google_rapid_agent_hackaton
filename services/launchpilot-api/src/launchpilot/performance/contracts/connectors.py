from typing import Protocol

from launchpilot.shared import PlatformProvider

from .platform import (
    CampaignMetricRequest,
    ConnectorFetchResult,
    ExternalAccount,
    ExternalCampaign,
)


class AdsConnector(Protocol):
    """Platform capability required for advertising discovery and collection."""

    @property
    def provider(self) -> PlatformProvider: ...

    def list_accounts(self, *, access_token: str) -> tuple[ExternalAccount, ...]: ...

    def list_campaigns(
        self, *, access_token: str, account_ref: str
    ) -> tuple[ExternalCampaign, ...]: ...

    def fetch_campaign_metrics(
        self, *, access_token: str, request: CampaignMetricRequest
    ) -> ConnectorFetchResult: ...
