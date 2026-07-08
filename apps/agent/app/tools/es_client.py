"""Real Elastic evidence via direct ES queries (httpx).

Reads the same data Java writes (contract 03): the `content_posts` index in
Elastic, authenticated with ELASTIC_API_KEY when provided. Returns normalized
evidence dicts consumed by the analyst/strategist tools.

Only ~tens of campaign posts per thread, so each call fetches the campaign's
posts once (size 500) and computes in Python — no reliance on field mappings or
aggregation quirks. Baseline is a recency split: latest-half vs earlier-half.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import httpx

from app.config import get_settings

log = logging.getLogger("launchpilot.es")

_CONTENT_POSTS = "content_posts"
_TEAM_NOTES = "team_notes"


def _ok(tool_name: str, mcp_tool: str, **extra) -> dict:
    return {"ok": True, "tool_name": tool_name, "mcp_tool": mcp_tool, "duration_ms": 0, **extra}


def _err(tool_name: str, code: str, message: str) -> dict:
    return {"ok": False, "tool_name": tool_name, "error_code": code, "error_message": message}


def _client() -> httpx.Client:
    s = get_settings()
    headers = {"Authorization": f"ApiKey {s.elastic_api_key}"} if s.elastic_api_key else {}
    return httpx.Client(
        base_url=s.elastic_url.rstrip("/"),
        headers=headers,
        timeout=15.0,
    )


def _scope_parts(scope):
    """Duck-type the EvidenceScope namedtuple (or None) into 6 fields."""
    if scope is None:
        return (None, None, None, None, None, None)
    return (
        scope.workspace_id, scope.campaign_id, scope.current_start,
        scope.current_end, scope.baseline_start, scope.baseline_end,
    )


def _tenancy_filters(workspace_id, campaign_id, since) -> list[dict]:
    # None-means-unfiltered: only add a clause when the value is present.
    filters: list[dict] = []
    if workspace_id is not None:
        filters.append({"term": {"workspace_id": workspace_id}})
    if campaign_id is not None:
        filters.append({"term": {"campaign_id": campaign_id}})
    if since is not None:
        filters.append({"range": {"published_at": {"gte": since}}})
    return filters


def _fetch_posts(workspace_id=None, campaign_id=None, since=None) -> list[dict]:
    # Scope to one campaign's posts server-side; `since` (the baseline window
    # start) bounds the span. The precise current/baseline split happens in
    # compute_baseline so date-boundary semantics live in one place.
    filters = _tenancy_filters(workspace_id, campaign_id, since)
    query = {"bool": {"filter": filters}} if filters else {"match_all": {}}
    body = {"size": 500, "query": query}
    with _client() as c:
        resp = c.post(f"/{_CONTENT_POSTS}/_search", json=body)
        resp.raise_for_status()
        hits = resp.json().get("hits", {}).get("hits", [])
    return [h.get("_source", {}) for h in hits]


def _metric_value(post: dict, metric: str):
    metrics = post.get("metrics") or {}
    return metrics.get(metric)


def _day(post: dict) -> str:
    # Normalize "2026-05-27T20:00:00+09:00" and "2026-05-27" to a comparable day.
    return str(post.get("published_at") or "")[:10]


def _window_means(rows, metric_name, cur_start, cur_end, base_start, base_end):
    """Mean over each date window; (None, None) when either side is too sparse."""
    cur = [float(_metric_value(p, metric_name)) for p in rows
           if cur_start <= _day(p) <= cur_end]
    base = [float(_metric_value(p, metric_name)) for p in rows
            if base_start <= _day(p) <= base_end]
    if len(cur) >= 2 and len(base) >= 2:
        return sum(cur) / len(cur), sum(base) / len(base)
    return None, None


def _recency_split(rows: list[dict], posts: list[dict], metric_name: str):
    """Latest-half vs earlier-half over the channel's posts (fallback path)."""
    values = [float(_metric_value(p, metric_name)) for p in rows]
    if len(values) >= 2:
        mid = len(values) // 2
        baseline = sum(values[:mid]) / mid
        recent = values[mid:]
        return sum(recent) / len(recent), baseline
    # Single post: baseline from the cross-channel mean of the same metric.
    current = values[0]
    cross = [
        float(_metric_value(p, metric_name))
        for p in posts if _metric_value(p, metric_name) is not None
    ]
    return current, ((sum(cross) / len(cross)) if cross else current)


def compute_baseline(
    posts: list[dict], metric_name: str, channel: str,
    current_start=None, current_end=None, baseline_start=None, baseline_end=None,
) -> dict:
    """Baseline over already-fetched posts (no I/O), shared by ES + MCP paths.

    When explicit windows are given (contract 04), current = mean over
    current_window, baseline = mean over baseline_window. Falls back to a
    recency split (latest-half vs earlier-half) when either window is too sparse
    (< 2 posts), so demo/sparse data still produces a lift.
    """
    rows = [
        p for p in posts
        if p.get("channel") == channel and _metric_value(p, metric_name) is not None
    ]
    if not rows:
        return _err("query_metric_baseline", "NO_EVIDENCE_FOUND",
                    f"no {metric_name} on {channel}")

    rows.sort(key=lambda p: _day(p))
    refs = [p.get("post_id") for p in rows if p.get("post_id")]

    current = baseline = None
    if current_start and baseline_start:
        current, baseline = _window_means(
            rows, metric_name,
            current_start, current_end or current_start,
            baseline_start, baseline_end or baseline_start)

    if current is None:
        # Imported CSVs often end days/weeks before today, leaving the
        # requested current window empty. Re-anchor the same 7d/28d shape
        # (contract 04 / windows.py) to the latest post day before giving up.
        latest = date.fromisoformat(_day(rows[-1]))
        current, baseline = _window_means(
            rows, metric_name,
            (latest - timedelta(days=6)).isoformat(), latest.isoformat(),
            (latest - timedelta(days=34)).isoformat(),
            (latest - timedelta(days=7)).isoformat())

    if current is None:  # still too sparse -> recency split
        current, baseline = _recency_split(rows, posts, metric_name)

    lift = round(current / baseline, 3) if baseline else 0.0
    return _ok(
        "query_metric_baseline", "esql",
        current_value=round(current, 6),
        baseline_value=round(baseline, 6),
        lift_ratio=lift,
        evidence_refs=refs[-5:],
    )


def top_content_refs(posts: list[dict], channels: list[str], metric_name: str) -> dict:
    """Pure top-by-metric content refs over already-fetched posts (no I/O)."""
    rows = [
        p for p in posts
        if p.get("channel") in channels and _metric_value(p, metric_name) is not None
    ]
    if not rows:
        return _err("search_content_posts", "NO_EVIDENCE_FOUND",
                    f"no {metric_name} posts on {channels}")
    rows.sort(key=lambda p: float(_metric_value(p, metric_name)), reverse=True)
    refs = [p.get("post_id") for p in rows[:5] if p.get("post_id")]
    return _ok("search_content_posts", "search", evidence_refs=refs)


def top_posts(metric_name: str, channel=None, scope=None, size: int = 5) -> dict:
    """Quick-Lookup: 지표 기준 상위 게시물을 제목과 함께 돌려준다 (no metric math).

    "어떤 게시물이 제일 잘됐어?"류 채팅 질문에 분석 라운드 없이 실제 제목으로
    답하기 위한 조회. search_content_posts와 달리 post id뿐 아니라 title·수치를
    포함한다.
    """
    ws, camp, _cs, _ce, _bs, _be = _scope_parts(scope)
    try:
        posts = _fetch_posts(ws, camp)
    except Exception as exc:  # noqa: BLE001 - network/auth failures are tool errors
        log.warning("ES top_posts failed: %s", exc)
        return _err("top_posts", "SEARCH_FAILED", str(exc))
    rows = [
        p for p in posts
        if (not channel or p.get("channel") == channel)
        and _metric_value(p, metric_name) is not None
    ]
    if not rows:
        return _err("top_posts", "NO_EVIDENCE_FOUND", f"no {metric_name} posts")
    rows.sort(key=lambda p: float(_metric_value(p, metric_name)), reverse=True)
    top = [
        {
            "post_id": p.get("post_id"),
            "title": p.get("title"),
            "channel": p.get("channel"),
            "published_at": _day(p),
            "value": float(_metric_value(p, metric_name)),
        }
        for p in rows[:size]
    ]
    return _ok(
        "top_posts", "search",
        metric_name=metric_name,
        posts=top,
        evidence_refs=[p["post_id"] for p in top if p["post_id"]],
    )


def data_inventory(workspace_id=None, campaign_id=None) -> dict:
    """Quick-Lookup: what stored data exists for a campaign (no metric math).

    Summarizes the campaign's content_posts — per-channel counts, available
    metric keys, and the covered date span. Feeds the chat path ("what data do
    you have") and the analysis-start guard, which accepts stored data as
    analysis input rather than demanding a fresh CSV attachment.
    """
    try:
        posts = _fetch_posts(workspace_id, campaign_id)
    except Exception as exc:  # noqa: BLE001 - network/auth failures are tool errors
        log.warning("ES data_inventory failed: %s", exc)
        return _err("data_inventory", "SEARCH_FAILED", str(exc))
    if not posts:
        return _err("data_inventory", "NO_EVIDENCE_FOUND", "no stored posts for this campaign")

    channels: dict[str, int] = {}
    metrics: set[str] = set()
    days: list[str] = []
    for post in posts:
        channel = post.get("channel") or "unknown"
        channels[channel] = channels.get(channel, 0) + 1
        metrics.update(k for k, v in (post.get("metrics") or {}).items() if v is not None)
        day = _day(post)
        if day:
            days.append(day)
    return _ok(
        "data_inventory", "search",
        post_count=len(posts),
        channels=dict(sorted(channels.items())),
        metrics=sorted(metrics),
        date_start=min(days) if days else None,
        date_end=max(days) if days else None,
    )


def query_metric_baseline(metric_name: str, channel: str, scope=None) -> dict:
    ws, camp, cur_start, cur_end, base_start, base_end = _scope_parts(scope)
    try:
        posts = _fetch_posts(ws, camp, base_start)
    except Exception as exc:  # noqa: BLE001 - network/auth failures are tool errors
        log.warning("ES query_metric_baseline failed: %s", exc)
        return _err("query_metric_baseline", "SEARCH_FAILED", str(exc))
    return compute_baseline(posts, metric_name, channel,
                            cur_start, cur_end, base_start, base_end)


def search_content_posts(channels: list[str], metric_name: str, scope=None) -> dict:
    ws, camp, _cs, _ce, base_start, _be = _scope_parts(scope)
    try:
        posts = _fetch_posts(ws, camp, base_start)
    except Exception as exc:  # noqa: BLE001
        log.warning("ES search_content_posts failed: %s", exc)
        return _err("search_content_posts", "SEARCH_FAILED", str(exc))
    return top_content_refs(posts, channels, metric_name)


def search_team_notes(query: str, scope=None) -> dict:
    ws, camp, _cs, _ce, _bs, _be = _scope_parts(scope)
    must = [{"multi_match": {"query": query, "fields": ["*"]}}]
    filters = []
    if ws is not None:
        filters.append({"term": {"workspace_id": ws}})
    if camp is not None:
        filters.append({"term": {"campaign_id": camp}})
    body = {"size": 5, "query": {"bool": {"must": must, "filter": filters}}}
    try:
        with _client() as c:
            resp = c.post(f"/{_TEAM_NOTES}/_search", json=body)
            if resp.status_code == 404:
                return _err("search_team_notes", "INDEX_UNAVAILABLE", "team_notes not indexed")
            resp.raise_for_status()
            hits = resp.json().get("hits", {}).get("hits", [])
    except Exception as exc:  # noqa: BLE001
        log.warning("ES search_team_notes failed: %s", exc)
        return _err("search_team_notes", "SEARCH_FAILED", str(exc))

    refs = [h.get("_id") for h in hits if h.get("_id")]
    if not refs:
        return _err("search_team_notes", "NO_EVIDENCE_FOUND", "no matching team notes")
    return _ok("search_team_notes", "search", evidence_refs=refs)


def load_growth_brief_context(parent_brief_id: str) -> dict:
    # Continuity context is optional; return empty rather than failing the run.
    return _ok("load_growth_brief_context", "search", evidence_refs=[])
