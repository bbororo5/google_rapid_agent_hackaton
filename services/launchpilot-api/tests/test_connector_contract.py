from datetime import date

import pytest

from launchpilot.domain.errors import DomainError
from launchpilot.domain.integrations import (
    CampaignMetricRequest,
    ConnectorFetchResult,
    ExternalAccount,
    ExternalCampaign,
    PlatformProvider,
)
from launchpilot.domain.models import DateRange, PlatformSlice


def test_external_account_requires_platform_identity() -> None:
    with pytest.raises(DomainError, match="account identity"):
        ExternalAccount(
            provider=PlatformProvider.GOOGLE_ADS,
            account_ref=" ",
            name="Google Ads Account",
        )


def test_external_campaign_keeps_provider_account_and_campaign_identity() -> None:
    campaign = ExternalCampaign(
        provider=PlatformProvider.META_ADS,
        account_ref="act_123",
        campaign_ref="456",
        name="Launch",
        status="ACTIVE",
    )

    assert campaign.provider is PlatformProvider.META_ADS
    assert campaign.account_ref == "act_123"
    assert campaign.campaign_ref == "456"


def test_campaign_metric_request_rejects_blank_fetch_reference() -> None:
    with pytest.raises(DomainError, match="request identity"):
        CampaignMetricRequest(
            account_ref="customers/123",
            campaign_ref="456",
            period=DateRange(date(2026, 7, 1), date(2026, 7, 31)),
            fetch_run_ref=" ",
        )


def test_connector_result_rejects_blank_warning() -> None:
    with pytest.raises(DomainError, match="warning"):
        ConnectorFetchResult(
            platform_slice=PlatformSlice(
                surface="GOOGLE_ADS",
                connector="google-ads",
                account_ref="customers/123",
                fetch_run_ref="run-1",
                metrics=(),
            ),
            warnings=(" ",),
        )
