from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from launchpilot.bootstrap.config import Settings
from launchpilot.devtools.mock_platforms.main import app as mock_app
from launchpilot.domain.integrations import CampaignMetricRequest
from launchpilot.domain.models import DateRange
from launchpilot.performance.adapters.google_ads import GoogleAdsConnector
from launchpilot.performance.adapters.meta_ads import MetaAdsConnector
from launchpilot.performance.adapters.youtube import YouTubeAnalyticsConnector


def mock_http_client() -> httpx.Client:
    api = TestClient(mock_app)

    def handler(request: httpx.Request) -> httpx.Response:
        response = api.request(
            request.method,
            request.url.raw_path.decode(),
            headers=dict(request.headers),
            content=request.content,
            follow_redirects=False,
        )
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            content=response.content,
            request=request,
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_mock_scenario_maps_one_business_campaign_to_all_platforms() -> None:
    client = TestClient(mock_app)

    scenario = client.get("/scenario").json()
    executions = scenario["platform_executions"]

    assert scenario["business_campaign"]["name"] == "LunchPilot 여름 신규고객 캠페인"
    assert set(executions) == {"GOOGLE_ADS", "META_ADS", "YOUTUBE"}
    assert executions["GOOGLE_ADS"]["campaign_ref"] == "910001"
    assert executions["META_ADS"]["campaign_ref"] == "920001"
    assert executions["YOUTUBE"]["account_ref"] == (
        "youtube-channel:UC_LUNCHPILOT_DEMO"
    )


def test_real_connectors_consume_mock_server_contracts() -> None:
    client = mock_http_client()
    period = DateRange(date(2026, 7, 1), date(2026, 7, 31))
    google = GoogleAdsConnector(
        developer_token="mock-developer-token",
        base_url="http://platform.mock/google",
        client=client,
    )
    meta = MetaAdsConnector(
        primary_conversion_action="purchase",
        base_url="http://platform.mock/meta",
        client=client,
    )
    youtube = YouTubeAnalyticsConnector(
        channels_url="http://platform.mock/youtube/v3/channels",
        analytics_url="http://platform.mock/youtube/analytics/v2/reports",
        client=client,
    )

    google_account = google.list_accounts(access_token="mock-token")[0]
    google_campaign = google.list_campaigns(
        access_token="mock-token", account_ref=google_account.account_ref
    )[0]
    google_result = google.fetch_campaign_metrics(
        access_token="mock-token",
        request=CampaignMetricRequest(
            account_ref=google_account.account_ref,
            campaign_ref=google_campaign.campaign_ref,
            period=period,
            fetch_run_ref="mock-google-run",
        ),
    )

    meta_account = meta.list_accounts(access_token="mock-token")[0]
    meta_campaign = meta.list_campaigns(
        access_token="mock-token", account_ref=meta_account.account_ref
    )[0]
    meta_result = meta.fetch_campaign_metrics(
        access_token="mock-token",
        request=CampaignMetricRequest(
            account_ref=meta_account.account_ref,
            campaign_ref=meta_campaign.campaign_ref,
            period=period,
            fetch_run_ref="mock-meta-run",
        ),
    )
    youtube_result = youtube.fetch_channel_metrics(
        access_token="mock-token",
        period=period,
        fetch_run_ref="mock-youtube-run",
    )

    assert "LunchPilot" in google_campaign.name
    assert "LunchPilot" in meta_campaign.name
    assert google_result.platform_slice.currency_code == "KRW"
    assert meta_result.platform_slice.currency_code == "KRW"
    assert youtube_result.channel_title == "LunchPilot"
    for result in (google_result, meta_result):
        values = {
            metric.metric_key: metric.value for metric in result.platform_slice.metrics
        }
        assert values["impressions"] > 0
        assert values["spend"] > 0
        assert values["conversions"] > 0
    youtube_values = {
        metric.metric_key: metric.value
        for metric in youtube_result.platform_slice.metrics
    }
    assert youtube_values["views"] > 0


def test_mock_meta_performance_exposes_the_known_creative_fatigue() -> None:
    client = mock_http_client()
    connector = MetaAdsConnector(
        primary_conversion_action="purchase",
        base_url="http://platform.mock/meta",
        client=client,
    )

    def metrics(start: date, end: date) -> dict[str, float]:
        result = connector.fetch_campaign_metrics(
            access_token="mock-token",
            request=CampaignMetricRequest(
                account_ref="act_2003004005",
                campaign_ref="920001",
                period=DateRange(start, end),
                fetch_run_ref=f"mock-meta-{start}",
            ),
        )
        return {
            metric.metric_key: metric.value for metric in result.platform_slice.metrics
        }

    before = metrics(date(2026, 7, 1), date(2026, 7, 16))
    after = metrics(date(2026, 7, 17), date(2026, 7, 31))

    assert before["clicks"] / before["impressions"] > (
        after["clicks"] / after["impressions"]
    )
    assert before["conversions"] / before["clicks"] > (
        after["conversions"] / after["clicks"]
    )


def test_mock_oauth_authorization_returns_to_launchpilot_callback() -> None:
    client = TestClient(mock_app)

    response = client.get(
        "/google/o/oauth2/v2/auth",
        params={
            "redirect_uri": "http://127.0.0.1:8000/auth/google/callback",
            "state": "signed-state",
        },
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"].startswith(
        "http://127.0.0.1:8000/auth/google/callback?"
    )
    assert "state=signed-state" in response.headers["location"]
    assert "code=mock-google-code" in response.headers["location"]


def test_mock_mode_rejects_remote_token_destination(monkeypatch) -> None:
    monkeypatch.setenv("PLATFORM_MOCK_BASE_URL", "https://untrusted.example")

    with pytest.raises(RuntimeError, match="must be an origin on localhost"):
        Settings.from_environment()
