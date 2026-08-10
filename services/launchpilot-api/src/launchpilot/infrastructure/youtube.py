from __future__ import annotations

from dataclasses import dataclass

import httpx

from launchpilot.domain.models import DateRange, MetricObservation, PlatformSlice

YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
YOUTUBE_ANALYTICS_URL = "https://youtubeanalytics.googleapis.com/v2/reports"
CORE_METRICS = (
    "views",
    "likes",
    "comments",
    "shares",
    "estimatedMinutesWatched",
    "averageViewDuration",
    "subscribersGained",
    "subscribersLost",
)


@dataclass(frozen=True, slots=True)
class YouTubeFetchResult:
    platform_slice: PlatformSlice
    channel_title: str | None


class YouTubeAnalyticsConnector:
    """Read-only normalizer for a user's owned YouTube channel metrics."""

    def __init__(
        self,
        *,
        channels_url: str = YOUTUBE_CHANNELS_URL,
        analytics_url: str = YOUTUBE_ANALYTICS_URL,
        client: httpx.Client | None = None,
    ) -> None:
        self._channels_url = channels_url
        self._analytics_url = analytics_url
        self._client = client or httpx.Client(timeout=30)

    def fetch_channel_metrics(
        self, *, access_token: str, period: DateRange, fetch_run_ref: str
    ) -> YouTubeFetchResult:
        headers = {"Authorization": f"Bearer {access_token}"}
        channel_response = self._client.get(
            self._channels_url,
            params={"part": "snippet", "mine": "true"},
            headers=headers,
        )
        channel_response.raise_for_status()
        channels = channel_response.json().get("items", [])
        if not channels:
            raise RuntimeError(
                "No owned YouTube channel was returned for this connection."
            )
        channel = channels[0]
        channel_id = channel["id"]
        analytics_response = self._client.get(
            self._analytics_url,
            params={
                "ids": "channel==MINE",
                "startDate": period.start.isoformat(),
                "endDate": period.end.isoformat(),
                "metrics": ",".join(CORE_METRICS),
            },
            headers=headers,
        )
        analytics_response.raise_for_status()
        payload = analytics_response.json()
        columns = [column["name"] for column in payload.get("columnHeaders", [])]
        rows = payload.get("rows", [])
        if not rows:
            raise RuntimeError(
                "YouTube Analytics returned no metrics for the requested period."
            )
        values = dict(zip(columns, rows[0], strict=True))
        metrics = tuple(
            MetricObservation(
                subject_ref=f"youtube-channel:{channel_id}",
                subject_level="CHANNEL",
                metric_key=key,
                value=float(value),
                unit="seconds" if key == "averageViewDuration" else "count",
                period=period,
                provenance_ref=f"youtube-analytics:{fetch_run_ref}",
            )
            for key, value in values.items()
        )
        return YouTubeFetchResult(
            platform_slice=PlatformSlice(
                surface="YOUTUBE",
                connector="youtube-analytics-v2",
                account_ref=f"youtube-channel:{channel_id}",
                fetch_run_ref=fetch_run_ref,
                metrics=metrics,
            ),
            channel_title=channel.get("snippet", {}).get("title"),
        )
