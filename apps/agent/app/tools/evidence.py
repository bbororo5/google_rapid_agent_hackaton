"""LaunchPilot Evidence Wrapper (contract 04).

Four read-only, domain-safe tools the ADK workers call. They never expose raw
DSL/ES|QL; they return normalized evidence dicts shaped exactly like the
contract responses (ok / tool_name / mcp_tool / evidence_refs / duration_ms).

Caller ownership (agent-tool-spec §1):
- query_metric_baseline, search_content_posts -> Analyst
- search_team_notes                            -> Strategist
- load_growth_brief_context                    -> Orchestrator (pre-injection)

STUB mode serves seed data. Real Elastic MCP wiring is the documented next step
(app/tools/mcp_client.py); when ELASTIC_MCP_URL is set those calls take over.
"""
from __future__ import annotations

from app.config import get_settings
from app.tools import seed


def _ok(tool_name: str, mcp_tool: str, **extra) -> dict:
    return {"ok": True, "tool_name": tool_name, "mcp_tool": mcp_tool, "duration_ms": 5, **extra}


def _err(tool_name: str, code: str, message: str, retryable: bool = False) -> dict:
    return {
        "ok": False,
        "tool_name": tool_name,
        "error": {"code": code, "message": message, "retryable": retryable},
        "duration_ms": 2,
    }


def query_metric_baseline(metric_name: str, channel: str) -> dict:
    """Compute how far a metric has moved vs its prior-window baseline.

    Args:
        metric_name: e.g. "save_rate", "shares", "views".
        channel: one of youtube, tiktok, instagram, x.

    Returns a dict with current_value, baseline_value, lift_ratio and an
    evidence_ref id. Used by the Analyst to detect performance signals.
    """
    if get_settings().use_real_elastic:
        from app.tools import mcp_client

        return mcp_client.query_metric_baseline(metric_name, channel)

    base = seed.METRIC_BASELINES.get((metric_name, channel))
    if base is None:
        return _err("query_metric_baseline", "NO_EVIDENCE_FOUND", f"no baseline for {metric_name}/{channel}")
    current, baseline = base["current_value"], base["baseline_value"]
    lift = round(current / baseline, 3) if baseline else 0.0
    ref = f"metric_{metric_name}_{channel}"
    return _ok(
        "query_metric_baseline",
        "esql",
        metric_name=metric_name,
        channel=channel,
        current_value=current,
        baseline_value=baseline,
        lift_ratio=lift,
        evidence_refs=[ref],
    )


def search_content_posts(channels: list[str], metric_name: str) -> dict:
    """Find the source posts behind a signal, for grounding.

    Args:
        channels: channels to include, e.g. ["tiktok", "youtube"].
        metric_name: the metric of interest, e.g. "save_rate".

    Returns evidence_refs pointing to content_post ids. Used by the Analyst.
    """
    if get_settings().use_real_elastic:
        from app.tools import mcp_client

        return mcp_client.search_content_posts(channels, metric_name)

    wanted = set(channels) if channels else None
    refs = [
        p["post_id"]
        for p in seed.CONTENT_POSTS
        if (wanted is None or p["channel"] in wanted) and metric_name in p["metrics"]
    ]
    return _ok("search_content_posts", "search", evidence_refs=refs)


def search_team_notes(query: str) -> dict:
    """Search qualitative team notes for the 'why' behind a signal.

    Args:
        query: free-text, e.g. "save rate spike" or "BTS".

    Returns team_note evidence_refs, or ok:false NO_EVIDENCE_FOUND when nothing
    matches. Used by the Strategist. If no notes are seeded at all the wrapper
    must not hallucinate (contract 04).
    """
    if get_settings().use_real_elastic:
        from app.tools import mcp_client

        return mcp_client.search_team_notes(query)

    if not seed.TEAM_NOTES:
        return _err("search_team_notes", "INDEX_UNAVAILABLE", "team_notes not seeded")
    terms = [t for t in query.lower().split() if t]
    refs = [
        n["note_id"]
        for n in seed.TEAM_NOTES
        if not terms or any(t in n["text"].lower() for t in terms)
    ]
    if not refs:
        return _err("search_team_notes", "NO_EVIDENCE_FOUND", "no matching team notes")
    return _ok("search_team_notes", "search", evidence_refs=refs)


def load_growth_brief_context(parent_brief_id: str) -> dict:
    """Load a prior approved brief for continuity (parent_brief_id).

    Caller: Orchestrator only, at session start. Continuity (R12/R13) is not
    implemented yet, so this returns an empty context in stub mode.
    """
    if get_settings().use_real_elastic:
        from app.tools import mcp_client

        return mcp_client.load_growth_brief_context(parent_brief_id)

    return _ok("load_growth_brief_context", "search", evidence_refs=[], brief=None)
