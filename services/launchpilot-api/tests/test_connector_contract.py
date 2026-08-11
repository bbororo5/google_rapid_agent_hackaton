from datetime import date
from uuid import uuid4

import pytest

from launchpilot.campaigns.public import ExternalCampaignBinding
from launchpilot.performance.models import PlatformSlice
from launchpilot.performance.public import (
    CampaignMetricRequest,
    ConnectorFetchResult,
    ExternalAccount,
    ExternalCampaign,
    PlatformProvider,
)
from launchpilot.shared import DateRange
from launchpilot.shared.errors import DomainError


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


def test_external_campaign_binding_keeps_comparison_context() -> None:
    binding = ExternalCampaignBinding.create(
        campaign_id=uuid4(),
        connection_id="connection-1",
        provider=PlatformProvider.GOOGLE_ADS,
        external_account_ref="customers/123",
        external_campaign_ref="456",
        display_name="Launch Search",
        currency_code="KRW",
        timezone="Asia/Seoul",
        attribution_setting="last-click",
    )

    assert binding.currency_code == "KRW"
    assert binding.timezone == "Asia/Seoul"
    assert binding.attribution_setting == "last-click"
