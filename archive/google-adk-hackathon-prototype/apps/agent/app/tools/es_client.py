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
        cur = [float(_metric_value(p, metric_name)) for p in rows
               if current_start <= _day(p) <= (current_end or current_start)]
        base = [float(_metric_value(p, metric_name)) for p in rows
                if baseline_start <= _day(p) <= (baseline_end or baseline_start)]
        if len(cur) >= 2 and len(base) >= 2:
            current = sum(cur) / len(cur)
            baseline = sum(base) / len(base)

    if current is None:  # no windows, or too sparse -> recency split
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
