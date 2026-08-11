import json
from datetime import date

import httpx

from launchpilot.performance.adapters.google_ads import GoogleAdsConnector
from launchpilot.performance.contracts.platform import CampaignMetricRequest
from launchpilot.shared import DateRange


def google_ads_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={"resourceNames": ["customers/123"]},
                request=request,
            )
        query = json.loads(request.content)["query"]
        if "FROM customer" in query:
            payload = {
                "results": [
                    {
                        "customer": {
                            "id": "123",
                            "descriptiveName": "Launch Account",
                            "currencyCode": "KRW",
                            "timeZone": "Asia/Seoul",
                        }
                    }
                ]
            }
        elif "metrics.impressions" in query:
            payload = {
                "results": [
                    {
                        "campaign": {"id": "456"},
                        "customer": {
                            "currencyCode": "KRW",
                            "timeZone": "Asia/Seoul",
                        },
                        "metrics": {
                            "impressions": "1000",
                            "clicks": "50",
                            "costMicros": "12500000",
                            "conversions": 4.0,
                            "conversionsValue": 80000.0,
                            "videoTrueviewViews": "300",
                        },
                    }
                ]
            }
        else:
            payload = {
                "results": [
                    {
                        "campaign": {
                            "id": "456",
                            "name": "Launch Search",
                            "status": "ENABLED",
                        }
                    }
                ]
            }
        return httpx.Response(200, json=payload, request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_google_ads_lists_accounts_and_campaigns() -> None:
    connector = GoogleAdsConnector(
        developer_token="developer-token", client=google_ads_client()
    )

    accounts = connector.list_accounts(access_token="access-token")
    campaigns = connector.list_campaigns(
        access_token="access-token", account_ref=accounts[0].account_ref
    )

    assert accounts[0].name == "Launch Account"
    assert accounts[0].currency_code == "KRW"
    assert campaigns[0].campaign_ref == "456"
    assert campaigns[0].status == "ENABLED"


def test_google_ads_normalizes_campaign_metrics() -> None:
    connector = GoogleAdsConnector(
        developer_token="developer-token", client=google_ads_client()
    )
    result = connector.fetch_campaign_metrics(
        access_token="access-token",
        request=CampaignMetricRequest(
            account_ref="customers/123",
            campaign_ref="456",
            period=DateRange(date(2026, 7, 1), date(2026, 7, 31)),
            fetch_run_ref="run-1",
        ),
    )

    metrics = {
        metric.metric_key: metric.value for metric in result.platform_slice.metrics
    }
    assert metrics["spend"] == 12.5
    assert metrics["impressions"] == 1000
    assert metrics["conversions"] == 4
    assert metrics["google_ads.video_views"] == 300
    assert result.platform_slice.currency_code == "KRW"
    assert result.platform_slice.timezone == "Asia/Seoul"
