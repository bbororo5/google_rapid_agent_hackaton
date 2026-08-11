from __future__ import annotations

import json
from typing import Any

import httpx

from launchpilot.performance.contracts import (
    CampaignMetricRequest,
    ConnectorFetchResult,
    ExternalAccount,
    ExternalCampaign,
)
from launchpilot.performance.models import MetricObservation, PlatformSlice
from launchpilot.shared import PlatformProvider


class MetaAdsConnector:
    """Meta Marketing API adapter that preserves action-type semantics."""

    def __init__(
        self,
        *,
        api_version: str = "v24.0",
        primary_conversion_action: str | None = None,
        attribution_windows: tuple[str, ...] = ("7d_click", "1d_view"),
        base_url: str = "https://graph.facebook.com",
        client: httpx.Client | None = None,
    ) -> None:
        self._api_version = api_version
        self._primary_conversion_action = primary_conversion_action
        self._attribution_windows = attribution_windows
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=30)

    @property
    def provider(self) -> PlatformProvider:
        return PlatformProvider.META_ADS

    def _get_all(
        self,
        *,
        access_token: str,
        path: str,
        params: dict[str, str],
    ) -> list[dict[str, Any]]:
        url = f"{self._base_url}/{self._api_version}/{path.lstrip('/')}"
        headers = {"Authorization": f"Bearer {access_token}"}
        rows: list[dict[str, Any]] = []
        after: str | None = None
        while True:
            page_params = dict(params)
            if after:
                page_params["after"] = after
            response = self._client.get(url, headers=headers, params=page_params)
            response.raise_for_status()
            body = response.json()
            rows.extend(body.get("data", []))
            paging = body.get("paging", {})
            after = (
                paging.get("cursors", {}).get("after") if paging.get("next") else None
            )
            if not after:
                return rows

    def list_accounts(self, *, access_token: str) -> tuple[ExternalAccount, ...]:
        rows = self._get_all(
            access_token=access_token,
            path="me/adaccounts",
            params={"fields": "id,name,currency,timezone_name,account_status"},
        )
        return tuple(
            ExternalAccount(
                provider=self.provider,
                account_ref=row["id"],
                name=row["name"],
                currency_code=row.get("currency"),
                timezone=row.get("timezone_name"),
            )
            for row in rows
        )

    def list_campaigns(
        self, *, access_token: str, account_ref: str
    ) -> tuple[ExternalCampaign, ...]:
        rows = self._get_all(
            access_token=access_token,
            path=f"{account_ref}/campaigns",
            params={"fields": "id,name,status,effective_status"},
        )
        return tuple(
            ExternalCampaign(
                provider=self.provider,
                account_ref=account_ref,
                campaign_ref=row["id"],
                name=row["name"],
                status=row.get("effective_status") or row["status"],
            )
            for row in rows
        )

    @staticmethod
    def _action_values(rows: list[dict[str, Any]], field: str) -> dict[str, float]:
        values: dict[str, float] = {}
        for row in rows:
            for item in row.get(field, []):
                action_type = item["action_type"]
                values[action_type] = values.get(action_type, 0.0) + float(
                    item["value"]
                )
        return values

    def fetch_campaign_metrics(
        self, *, access_token: str, request: CampaignMetricRequest
    ) -> ConnectorFetchResult:
        rows = self._get_all(
            access_token=access_token,
            path=f"{request.campaign_ref}/insights",
            params={
                "fields": (
                    "campaign_id,account_currency,impressions,reach,clicks,spend,"
                    "actions,action_values"
                ),
                "level": "campaign",
                "time_range": json.dumps(
                    {
                        "since": request.period.start.isoformat(),
                        "until": request.period.end.isoformat(),
                    },
                    separators=(",", ":"),
                ),
                "action_attribution_windows": json.dumps(
                    self._attribution_windows, separators=(",", ":")
                ),
            },
        )
        if not rows:
            raise RuntimeError("Meta Ads returned no metrics for this campaign.")
        totals = {
            key: sum(float(row.get(key, 0)) for row in rows)
            for key in ("impressions", "reach", "clicks", "spend")
        }
        actions = self._action_values(rows, "actions")
        action_values = self._action_values(rows, "action_values")
        currency = rows[0].get("account_currency")
        subject_ref = f"meta-ads-campaign:{request.campaign_ref}"
        specs: list[tuple[str, float, str]] = [
            ("impressions", totals["impressions"], "count"),
            ("clicks", totals["clicks"], "count"),
            ("spend", totals["spend"], f"currency:{currency or 'UNKNOWN'}"),
            ("meta.reach", totals["reach"], "count"),
        ]
        specs.extend(
            (f"meta.actions.{action_type}", value, "count")
            for action_type, value in sorted(actions.items())
        )
        specs.extend(
            (
                f"meta.action_values.{action_type}",
                value,
                f"currency:{currency or 'UNKNOWN'}",
            )
            for action_type, value in sorted(action_values.items())
        )
        warnings = [
            "Meta action types are retained separately to prevent conversion double counting."
        ]
        if self._primary_conversion_action:
            specs.append(
                (
                    "conversions",
                    actions.get(self._primary_conversion_action, 0.0),
                    "count",
                )
            )
            specs.append(
                (
                    "conversion_value",
                    action_values.get(self._primary_conversion_action, 0.0),
                    f"currency:{currency or 'UNKNOWN'}",
                )
            )
        else:
            warnings.append(
                "Canonical conversions require a configured primary Meta action type."
            )
        metrics = tuple(
            MetricObservation(
                subject_ref=subject_ref,
                subject_level="CAMPAIGN",
                metric_key=key,
                value=value,
                unit=unit,
                period=request.period,
                provenance_ref=f"meta-ads:{request.fetch_run_ref}",
            )
            for key, value, unit in specs
        )
        return ConnectorFetchResult(
            platform_slice=PlatformSlice(
                surface="META_ADS",
                connector=f"meta-marketing-api-{self._api_version}",
                account_ref=request.account_ref,
                external_campaign_ref=request.campaign_ref,
                fetch_run_ref=request.fetch_run_ref,
                currency_code=currency,
                attribution_setting="+".join(self._attribution_windows),
                metrics=metrics,
            ),
            warnings=tuple(warnings),
        )
