from __future__ import annotations

from typing import Any

import httpx

from launchpilot.domain.integrations import (
    CampaignMetricRequest,
    ConnectorFetchResult,
    ExternalAccount,
    ExternalCampaign,
    PlatformProvider,
)
from launchpilot.domain.models import MetricObservation, PlatformSlice


class GoogleAdsConnector:
    """Thin Google Ads REST adapter with deterministic GAQL normalization."""

    def __init__(
        self,
        *,
        developer_token: str,
        api_version: str = "v25",
        login_customer_id: str | None = None,
        base_url: str = "https://googleads.googleapis.com",
        client: httpx.Client | None = None,
    ) -> None:
        if not developer_token.strip():
            raise ValueError("developer_token must not be blank")
        self._developer_token = developer_token
        self._api_version = api_version
        self._login_customer_id = login_customer_id
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=30)

    @property
    def provider(self) -> PlatformProvider:
        return PlatformProvider.GOOGLE_ADS

    def _headers(self, access_token: str) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "developer-token": self._developer_token,
            "Content-Type": "application/json",
        }
        if self._login_customer_id:
            headers["login-customer-id"] = self._login_customer_id
        return headers

    def _search(
        self, *, access_token: str, customer_id: str, query: str
    ) -> list[dict[str, Any]]:
        url = (
            f"{self._base_url}/{self._api_version}/customers/"
            f"{customer_id}/googleAds:search"
        )
        rows: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            payload: dict[str, str] = {"query": query}
            if page_token:
                payload["pageToken"] = page_token
            response = self._client.post(
                url, headers=self._headers(access_token), json=payload
            )
            response.raise_for_status()
            body = response.json()
            rows.extend(body.get("results", []))
            page_token = body.get("nextPageToken")
            if not page_token:
                return rows

    def list_accounts(self, *, access_token: str) -> tuple[ExternalAccount, ...]:
        response = self._client.get(
            f"{self._base_url}/{self._api_version}/customers:listAccessibleCustomers",
            headers=self._headers(access_token),
        )
        response.raise_for_status()
        accounts: list[ExternalAccount] = []
        for resource_name in response.json().get("resourceNames", []):
            customer_id = resource_name.rsplit("/", 1)[-1]
            rows = self._search(
                access_token=access_token,
                customer_id=customer_id,
                query=(
                    "SELECT customer.id, customer.descriptive_name, "
                    "customer.currency_code, customer.time_zone FROM customer LIMIT 1"
                ),
            )
            if not rows:
                continue
            customer = rows[0]["customer"]
            accounts.append(
                ExternalAccount(
                    provider=self.provider,
                    account_ref=f"customers/{customer['id']}",
                    name=customer.get("descriptiveName") or f"Google Ads {customer_id}",
                    currency_code=customer.get("currencyCode"),
                    timezone=customer.get("timeZone"),
                )
            )
        return tuple(accounts)

    def list_campaigns(
        self, *, access_token: str, account_ref: str
    ) -> tuple[ExternalCampaign, ...]:
        customer_id = account_ref.rsplit("/", 1)[-1]
        rows = self._search(
            access_token=access_token,
            customer_id=customer_id,
            query=(
                "SELECT campaign.id, campaign.name, campaign.status "
                "FROM campaign ORDER BY campaign.id"
            ),
        )
        return tuple(
            ExternalCampaign(
                provider=self.provider,
                account_ref=account_ref,
                campaign_ref=str(row["campaign"]["id"]),
                name=row["campaign"]["name"],
                status=row["campaign"]["status"],
            )
            for row in rows
        )

    def fetch_campaign_metrics(
        self, *, access_token: str, request: CampaignMetricRequest
    ) -> ConnectorFetchResult:
        customer_id = request.account_ref.rsplit("/", 1)[-1]
        rows = self._search(
            access_token=access_token,
            customer_id=customer_id,
            query=(
                "SELECT campaign.id, customer.currency_code, customer.time_zone, "
                "metrics.impressions, metrics.clicks, metrics.cost_micros, "
                "metrics.conversions, metrics.conversions_value, "
                "metrics.video_trueview_views "
                "FROM campaign "
                f"WHERE campaign.id = {request.campaign_ref} "
                f"AND segments.date BETWEEN '{request.period.start.isoformat()}' "
                f"AND '{request.period.end.isoformat()}'"
            ),
        )
        if not rows:
            raise RuntimeError("Google Ads returned no metrics for this campaign.")
        row = rows[0]
        raw_metrics = row.get("metrics", {})
        customer = row.get("customer", {})
        currency = customer.get("currencyCode")
        subject_ref = f"google-ads-campaign:{request.campaign_ref}"
        specs = (
            ("impressions", float(raw_metrics.get("impressions", 0)), "count"),
            ("clicks", float(raw_metrics.get("clicks", 0)), "count"),
            (
                "spend",
                float(raw_metrics.get("costMicros", 0)) / 1_000_000,
                f"currency:{currency or 'UNKNOWN'}",
            ),
            ("conversions", float(raw_metrics.get("conversions", 0)), "count"),
            (
                "conversion_value",
                float(raw_metrics.get("conversionsValue", 0)),
                f"currency:{currency or 'UNKNOWN'}",
            ),
            (
                "google_ads.video_views",
                float(raw_metrics.get("videoTrueviewViews", 0)),
                "count",
            ),
        )
        metrics = tuple(
            MetricObservation(
                subject_ref=subject_ref,
                subject_level="CAMPAIGN",
                metric_key=key,
                value=value,
                unit=unit,
                period=request.period,
                provenance_ref=f"google-ads:{request.fetch_run_ref}",
            )
            for key, value, unit in specs
        )
        return ConnectorFetchResult(
            platform_slice=PlatformSlice(
                surface="GOOGLE_ADS",
                connector=f"google-ads-rest-{self._api_version}",
                account_ref=request.account_ref,
                external_campaign_ref=request.campaign_ref,
                fetch_run_ref=request.fetch_run_ref,
                currency_code=currency,
                timezone=customer.get("timeZone"),
                attribution_setting=None,
                metrics=metrics,
            ),
            warnings=(
                "Conversion metrics retain the Google Ads account attribution settings.",
            ),
        )
