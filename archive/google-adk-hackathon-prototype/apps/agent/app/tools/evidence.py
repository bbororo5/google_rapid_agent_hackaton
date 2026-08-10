"""LaunchPilot Evidence Wrapper (contract 04).

Four read-only, domain-safe tools the ADK workers call. They never expose raw
DSL/ES|QL; they return normalized evidence dicts shaped exactly like the
contract responses (ok / tool_name / mcp_tool / evidence_refs / duration_ms).

Caller ownership:
- query_metric_baseline, search_content_posts -> Analyst
- search_team_notes                            -> Strategist
- load_growth_brief_context                    -> Orchestrator (pre-injection)

Backend is chosen per call with a 2-tier real-data path:
  1. Elastic MCP (mcp_client) when ELASTIC_USE_MCP is set  -> contract 04 method B
  2. direct ES (es_client) when ELASTIC_URL/API_KEY are set
A transport failure in tier 1 falls through to tier 2. Missing Elastic
configuration is a visible tool error; evidence is never fabricated locally.
"""
from __future__ import annotations

import contextlib
import contextvars
import logging
from typing import NamedTuple, Optional

from app.config import get_settings
from app import telemetry

log = logging.getLogger("launchpilot.evidence")


class EvidenceScope(NamedTuple):
    """Per-turn tenancy + analysis window, injected by the orchestrator.

    Sourced from the thread context (workspace/campaign) + the analysis window,
    NOT from the LLM. Threaded into every evidence backend so queries are scoped
    to one campaign's data. Any None field means "do not filter on this" so a
    context-less turn (e.g. unit tests) still sees all data.
    """

    workspace_id: Optional[str] = None
    campaign_id: Optional[str] = None
    current_start: Optional[str] = None
    current_end: Optional[str] = None
    baseline_start: Optional[str] = None
    baseline_end: Optional[str] = None


_EMPTY_SCOPE = EvidenceScope()
_SCOPE: contextvars.ContextVar[Optional[EvidenceScope]] = contextvars.ContextVar(
    "evidence_scope", default=None
)


@contextlib.contextmanager
def scope(
    workspace_id, campaign_id, current_start, current_end, baseline_start, baseline_end
):
    """Bind the evidence scope for the duration of a pipeline run."""
    token = _SCOPE.set(
        EvidenceScope(
            workspace_id, campaign_id, current_start, current_end, baseline_start, baseline_end
        )
    )
    try:
        yield
    finally:
        _SCOPE.reset(token)


def _current_scope() -> EvidenceScope:
    return _SCOPE.get() or _EMPTY_SCOPE


def _resolve(tool_name: str, mcp_fn, es_fn) -> dict:
    """Pick the evidence backend: MCP -> direct ES, with MCP fallback."""
    s = get_settings()
    if s.elastic_mcp_enabled:
        try:
            return mcp_fn()
        except Exception as exc:  # noqa: BLE001 - transport failure -> fall back
            log.warning("%s: MCP path failed, falling back: %s", tool_name, exc)
    if s.use_real_elastic:
        return es_fn()
    return _err(
        tool_name,
        "ELASTIC_UNCONFIGURED",
        "Elastic evidence is not configured.",
        retryable=False,
    )


def _stamp(span, result: dict) -> None:
    # RETRIEVER span output: map evidence_refs -> retrieval.documents (contract 06
    # §Retriever Span Contract; document.id == EvidenceRef.ref_id). Output value is
    # a concise summary, never raw rows (§Redaction).
    telemetry.record_evidence_result(span, result)


def _ok(tool_name: str, mcp_tool: str, **extra) -> dict:
    # Common success envelope (contract 04). `mcp_tool` names the underlying
    # generic Elastic MCP tool the wrapper would have used (esql/search).
    return {"ok": True, "tool_name": tool_name, "mcp_tool": mcp_tool, "duration_ms": 5, **extra}


def _err(tool_name: str, code: str, message: str, retryable: bool = False) -> dict:
    # Common failure envelope. `retryable` drives Class-1 retry policy (§4-A).
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
    sc = _current_scope()

    with telemetry.evidence_span(
        "launchpilot.evidence.query_metric_baseline",
        tool_name="query_metric_baseline",
        input_value={"metric_name": metric_name, "channel": channel},
    ) as span:
        from app.tools import es_client, mcp_client

        result = _resolve(
            "query_metric_baseline",
            lambda: mcp_client.query_metric_baseline(metric_name, channel, sc),
            lambda: es_client.query_metric_baseline(metric_name, channel, sc),
        )
        _stamp(span, result)
        return result


def search_content_posts(channels: list[str], metric_name: str) -> dict:
    """Find the source posts behind a signal, for grounding.

    Args:
        channels: channels to include, e.g. ["tiktok", "youtube"].
        metric_name: the metric of interest, e.g. "save_rate".

    Returns evidence_refs pointing to content_post ids. Used by the Analyst.
    """
    sc = _current_scope()

    with telemetry.evidence_span(
        "launchpilot.evidence.search_content_posts",
        tool_name="search_content_posts",
        input_value={"channels": channels, "metric_name": metric_name},
    ) as span:
        from app.tools import es_client, mcp_client

        result = _resolve(
            "search_content_posts",
            lambda: mcp_client.search_content_posts(channels, metric_name, sc),
            lambda: es_client.search_content_posts(channels, metric_name, sc),
        )
        _stamp(span, result)
        return result


def search_team_notes(query: str) -> dict:
    """Search qualitative team notes for the 'why' behind a signal.

    Args:
        query: free-text, e.g. "save rate spike" or "BTS".

    Returns team_note evidence_refs, or ok:false NO_EVIDENCE_FOUND when nothing
    matches. Used by the Strategist. Missing notes must surface as a tool error,
    never as invented qualitative evidence.
    """
    sc = _current_scope()

    with telemetry.evidence_span(
        "launchpilot.evidence.search_team_notes",
        tool_name="search_team_notes",
        input_value={"query": query},
    ) as span:
        from app.tools import es_client, mcp_client

        result = _resolve(
            "search_team_notes",
            lambda: mcp_client.search_team_notes(query, sc),
            lambda: es_client.search_team_notes(query, sc),
        )
        _stamp(span, result)
        return result


def load_growth_brief_context(parent_brief_id: str) -> dict:
    """Load a prior approved brief for continuity (parent_brief_id).

    Caller: Orchestrator only, at session start. Continuity (R12/R13) is not
    implemented yet, so this returns an empty context.
    """
    from app.tools import es_client, mcp_client

    return _resolve(
        "load_growth_brief_context",
        lambda: mcp_client.load_growth_brief_context(parent_brief_id),
        lambda: es_client.load_growth_brief_context(parent_brief_id),
    )
