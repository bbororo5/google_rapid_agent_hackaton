from __future__ import annotations

import json
import re
from datetime import date
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import Body, FastAPI, Query
from fastapi.responses import RedirectResponse

from .scenario import (
    SCENARIO_END,
    SCENARIO_START,
    google_daily,
    meta_daily,
    scenario_manifest,
    total,
    youtube_daily,
)

app = FastAPI(
    title="LaunchPilot Platform Mock",
    version="0.1.0",
    description="A deterministic Google Ads, Meta Ads and YouTube API simulator.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "scenario": "lunchpilot-summer-acquisition-2026"}


@app.get("/scenario")
def read_scenario() -> dict[str, object]:
    return scenario_manifest()


@app.get("/google/{api_version}/customers:listAccessibleCustomers")
def google_accounts(api_version: str) -> dict[str, list[str]]:
    return {"resourceNames": ["customers/1002003004"]}


def _google_period(query: str) -> tuple[date, date]:
    matched = re.search(
        r"BETWEEN '(\d{4}-\d{2}-\d{2})' AND '(\d{4}-\d{2}-\d{2})'", query
    )
    if not matched:
        return SCENARIO_START, SCENARIO_END
    return date.fromisoformat(matched.group(1)), date.fromisoformat(matched.group(2))


@app.post("/google/{api_version}/customers/{customer_id}/googleAds:search")
def google_search(
    api_version: str,
    customer_id: str,
    payload: Annotated[dict[str, Any], Body()],
) -> dict[str, object]:
    if customer_id != "1002003004":
        return {"results": []}
    query = str(payload.get("query", ""))
    customer = {
        "id": "1002003004",
        "descriptiveName": "LunchPilot Growth Account",
        "currencyCode": "KRW",
        "timeZone": "Asia/Seoul",
    }
    if "FROM customer" in query:
        return {"results": [{"customer": customer}]}
    campaign = {
        "id": "910001",
        "name": "[LunchPilot] 여름 신규고객 | Search + Video",
        "status": "ENABLED",
    }
    if "metrics.impressions" not in query:
        return {"results": [{"campaign": campaign}]}
    if "campaign.id = 910001" not in query:
        return {"results": []}
    start, end = _google_period(query)
    rows = google_daily(start, end)
    if not rows:
        return {"results": []}
    return {
        "results": [
            {
                "campaign": {"id": campaign["id"]},
                "customer": customer,
                "metrics": {
                    "impressions": str(round(total(rows, "impressions"))),
                    "clicks": str(round(total(rows, "clicks"))),
                    "costMicros": str(round(total(rows, "spend") * 1_000_000)),
                    "conversions": round(total(rows, "conversions"), 1),
                    "conversionsValue": round(total(rows, "conversion_value")),
                    "videoTrueviewViews": str(round(total(rows, "video_views"))),
                },
            }
        ]
    }


@app.get("/meta/{api_version}/me/adaccounts")
def meta_accounts(api_version: str) -> dict[str, object]:
    return {
        "data": [
            {
                "id": "act_2003004005",
                "name": "LunchPilot Meta Business",
                "currency": "KRW",
                "timezone_name": "Asia/Seoul",
                "account_status": 1,
            }
        ]
    }


@app.get("/meta/{api_version}/act_2003004005/campaigns")
def meta_campaigns(api_version: str) -> dict[str, object]:
    return {
        "data": [
            {
                "id": "920001",
                "name": "[LunchPilot] 여름 신규고객 | Reels + Feed",
                "status": "ACTIVE",
                "effective_status": "ACTIVE",
            }
        ]
    }


@app.get("/meta/{api_version}/920001/insights")
def meta_insights(
    api_version: str,
    time_range: Annotated[str | None, Query()] = None,
) -> dict[str, object]:
    period = json.loads(time_range) if time_range else {}
    start = date.fromisoformat(period.get("since", SCENARIO_START.isoformat()))
    end = date.fromisoformat(period.get("until", SCENARIO_END.isoformat()))
    rows = meta_daily(start, end)
    if not rows:
        return {"data": []}
    clicks = round(total(rows, "clicks"))
    purchases = round(total(rows, "conversions"))
    purchase_value = round(total(rows, "conversion_value"))
    return {
        "data": [
            {
                "campaign_id": "920001",
                "account_currency": "KRW",
                "impressions": str(round(total(rows, "impressions"))),
                "reach": str(round(total(rows, "reach"))),
                "clicks": str(clicks),
                "spend": str(round(total(rows, "spend"))),
                "actions": [
                    {"action_type": "link_click", "value": str(clicks)},
                    {"action_type": "purchase", "value": str(purchases)},
                ],
                "action_values": [
                    {"action_type": "purchase", "value": str(purchase_value)}
                ],
            }
        ]
    }


@app.get("/youtube/v3/channels")
def youtube_channels() -> dict[str, object]:
    return {
        "items": [
            {
                "id": "UC_LUNCHPILOT_DEMO",
                "snippet": {"title": "LunchPilot"},
            }
        ]
    }


@app.get("/youtube/analytics/v2/reports")
def youtube_analytics(
    start_date: Annotated[date, Query(alias="startDate")],
    end_date: Annotated[date, Query(alias="endDate")],
    metrics: Annotated[str, Query()],
) -> dict[str, object]:
    rows = youtube_daily(start_date, end_date)
    if not rows:
        return {"columnHeaders": [], "rows": []}
    metric_names = metrics.split(",")
    values = []
    for name in metric_names:
        if name == "averageViewDuration":
            values.append(round(sum(row[name] for row in rows) / len(rows)))
        else:
            values.append(sum(row[name] for row in rows))
    return {
        "columnHeaders": [{"name": name} for name in metric_names],
        "rows": [values],
    }


def _oauth_redirect(redirect_uri: str, state: str, code: str) -> RedirectResponse:
    separator = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(
        f"{redirect_uri}{separator}{urlencode({'state': state, 'code': code})}"
    )


@app.get("/google/o/oauth2/v2/auth")
def google_authorize(
    redirect_uri: Annotated[str, Query()], state: Annotated[str, Query()]
) -> RedirectResponse:
    return _oauth_redirect(redirect_uri, state, "mock-google-code")


@app.post("/google/token")
def google_token() -> dict[str, object]:
    return {
        "access_token": "mock-google-access-token",
        "refresh_token": "mock-google-refresh-token",
        "expires_in": 3600,
        "token_type": "Bearer",
    }


@app.get("/google/userinfo")
def google_userinfo() -> dict[str, str]:
    return {
        "sub": "mock-launchpilot-user",
        "email": "marketer@lunchpilot.example",
        "name": "LunchPilot Marketer",
    }


@app.get("/meta/{api_version}/dialog/oauth")
def meta_authorize(
    api_version: str,
    redirect_uri: Annotated[str, Query()],
    state: Annotated[str, Query()],
) -> RedirectResponse:
    return _oauth_redirect(redirect_uri, state, "mock-meta-code")


@app.get("/meta/{api_version}/oauth/access_token")
def meta_token(api_version: str) -> dict[str, object]:
    return {
        "access_token": "mock-meta-access-token",
        "expires_in": 5_184_000,
        "token_type": "bearer",
    }
