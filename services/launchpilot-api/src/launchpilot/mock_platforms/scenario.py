from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

SCENARIO_START = date(2026, 7, 1)
SCENARIO_END = date(2026, 7, 31)


@dataclass(frozen=True, slots=True)
class DailyMetrics:
    day: date
    impressions: int
    clicks: int
    spend: int
    conversions: float
    conversion_value: int
    reach: int = 0
    video_views: int = 0


def scenario_manifest() -> dict[str, object]:
    """Describe one business campaign and its platform-specific executions."""
    return {
        "scenario_id": "lunchpilot-summer-acquisition-2026",
        "business_campaign": {
            "name": "LunchPilot 여름 신규고객 캠페인",
            "goal": "첫 주문 구매와 브랜드 검색 수요 확대",
            "period": {"start": SCENARIO_START, "end": SCENARIO_END},
            "currency": "KRW",
            "timezone": "Asia/Seoul",
            "planned_budget": 30_000_000,
        },
        "platform_executions": {
            "GOOGLE_ADS": {
                "account_ref": "customers/1002003004",
                "campaign_ref": "910001",
                "name": "[LunchPilot] 여름 신규고객 | Search + Video",
                "role": "구매 의도가 높은 검색 수요와 영상 광고",
            },
            "META_ADS": {
                "account_ref": "act_2003004005",
                "campaign_ref": "920001",
                "name": "[LunchPilot] 여름 신규고객 | Reels + Feed",
                "role": "신규 잠재고객 도달과 구매 전환",
            },
            "YOUTUBE": {
                "account_ref": "youtube-channel:UC_LUNCHPILOT_DEMO",
                "content_ref": "video-lunchpilot-summer-01",
                "name": "일주일 점심 고민을 줄이는 방법",
                "role": "같은 캠페인을 지원하는 소유 채널 콘텐츠",
            },
        },
        "known_event": {
            "date": date(2026, 7, 17),
            "description": "소재 피로가 시작되어 Meta CTR과 구매율이 하락",
        },
    }


def _days(start: date, end: date):
    current = max(start, SCENARIO_START)
    final = min(end, SCENARIO_END)
    while current <= final:
        yield current
        current += timedelta(days=1)


def google_daily(start: date, end: date) -> tuple[DailyMetrics, ...]:
    rows: list[DailyMetrics] = []
    for day in _days(start, end):
        index = (day - SCENARIO_START).days
        weekend_factor = 0.88 if day.weekday() >= 5 else 1.0
        impressions = round((18_000 + index * 110) * weekend_factor)
        ctr = 0.043 if day.day < 17 else 0.038
        clicks = round(impressions * ctr)
        conversions = round(clicks * (0.056 if day.day < 17 else 0.051), 1)
        rows.append(
            DailyMetrics(
                day=day,
                impressions=impressions,
                clicks=clicks,
                spend=round(clicks * 650),
                conversions=conversions,
                conversion_value=round(conversions * 28_500),
                video_views=round(impressions * 0.22),
            )
        )
    return tuple(rows)


def meta_daily(start: date, end: date) -> tuple[DailyMetrics, ...]:
    rows: list[DailyMetrics] = []
    for day in _days(start, end):
        index = (day - SCENARIO_START).days
        weekend_factor = 1.08 if day.weekday() >= 5 else 1.0
        impressions = round((24_000 + index * 170) * weekend_factor)
        ctr = 0.0125 if day.day < 17 else 0.0086
        clicks = round(impressions * ctr)
        conversions = round(clicks * (0.031 if day.day < 17 else 0.018))
        rows.append(
            DailyMetrics(
                day=day,
                impressions=impressions,
                clicks=clicks,
                spend=round(clicks * 430),
                conversions=conversions,
                conversion_value=round(conversions * 28_500),
                reach=round(impressions * 0.72),
            )
        )
    return tuple(rows)


def youtube_daily(start: date, end: date) -> tuple[dict[str, int], ...]:
    rows: list[dict[str, int]] = []
    for day in _days(start, end):
        distance_from_release = abs((day - date(2026, 7, 10)).days)
        release_lift = max(0, 8_000 - distance_from_release * 760)
        views = 1_200 + release_lift
        rows.append(
            {
                "views": views,
                "likes": round(views * 0.047),
                "comments": round(views * 0.0032),
                "shares": round(views * 0.008),
                "estimatedMinutesWatched": round(views * 3.4),
                "averageViewDuration": 204,
                "subscribersGained": round(views * 0.006),
                "subscribersLost": round(views * 0.0004),
            }
        )
    return tuple(rows)


def total(rows: tuple[DailyMetrics, ...], field: str) -> float:
    return sum(float(getattr(row, field)) for row in rows)
