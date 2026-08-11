from datetime import date

import httpx

from launchpilot.domain.integrations import CampaignMetricRequest
from launchpilot.domain.models import DateRange
from launchpilot.performance.adapters.meta_ads import MetaAdsConnector


def meta_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/me/adaccounts"):
            payload = {
                "data": [
                    {
                        "id": "act_123",
                        "name": "Meta Launch",
                        "currency": "KRW",
                        "timezone_name": "Asia/Seoul",
                        "account_status": 1,
                    }
                ]
            }
        elif path.endswith("/act_123/campaigns"):
            payload = {
                "data": [
                    {
                        "id": "456",
                        "name": "Instagram Launch",
                        "status": "ACTIVE",
                        "effective_status": "ACTIVE",
                    }
                ]
            }
        else:
            payload = {
                "data": [
                    {
                        "campaign_id": "456",
                        "account_currency": "KRW",
                        "impressions": "2000",
                        "reach": "1500",
                        "clicks": "80",
                        "spend": "32.5",
                        "actions": [
                            {"action_type": "link_click", "value": "80"},
                            {"action_type": "purchase", "value": "5"},
                        ],
                        "action_values": [
                            {"action_type": "purchase", "value": "125000"}
                        ],
                    }
                ]
            }
        return httpx.Response(200, json=payload, request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_meta_ads_lists_accounts_and_campaigns() -> None:
    connector = MetaAdsConnector(client=meta_client())

    accounts = connector.list_accounts(access_token="access-token")
    campaigns = connector.list_campaigns(
        access_token="access-token", account_ref=accounts[0].account_ref
    )

    assert accounts[0].account_ref == "act_123"
    assert accounts[0].currency_code == "KRW"
    assert campaigns[0].campaign_ref == "456"


def test_meta_ads_preserves_actions_and_selects_primary_conversion() -> None:
    connector = MetaAdsConnector(
        primary_conversion_action="purchase", client=meta_client()
    )
    result = connector.fetch_campaign_metrics(
        access_token="access-token",
        request=CampaignMetricRequest(
            account_ref="act_123",
            campaign_ref="456",
            period=DateRange(date(2026, 7, 1), date(2026, 7, 31)),
            fetch_run_ref="run-1",
        ),
    )

    metrics = {
        metric.metric_key: metric.value for metric in result.platform_slice.metrics
    }
    assert metrics["spend"] == 32.5
    assert metrics["meta.actions.link_click"] == 80
    assert metrics["meta.actions.purchase"] == 5
    assert metrics["conversions"] == 5
    assert metrics["conversion_value"] == 125000
    assert result.platform_slice.currency_code == "KRW"
    assert result.platform_slice.attribution_setting == "7d_click+1d_view"


def test_meta_ads_does_not_invent_canonical_conversion_without_policy() -> None:
    result = MetaAdsConnector(client=meta_client()).fetch_campaign_metrics(
        access_token="access-token",
        request=CampaignMetricRequest(
            account_ref="act_123",
            campaign_ref="456",
            period=DateRange(date(2026, 7, 1), date(2026, 7, 31)),
            fetch_run_ref="run-2",
        ),
    )

    keys = {metric.metric_key for metric in result.platform_slice.metrics}
    assert "conversions" not in keys
    assert any("primary Meta action" in warning for warning in result.warnings)
