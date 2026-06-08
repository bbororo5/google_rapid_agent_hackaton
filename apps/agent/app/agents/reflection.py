"""Reflection read side via the Phoenix MCP server (contract 06 §Reflection).

The WRITE half (app/observability.py) exports run spans to Phoenix. This is the
READ half: at session start, query Phoenix for past reviewer/validation spans and
summarize recurring failure patterns. The summary is ADVISORY context only -- it
can inform but NEVER override the deterministic reviewer (ADR-0006 / contract 06
line169). It is emitted as an EVALUATOR span so it shows in the same trace tree.

Verified against @arizeai/phoenix-mcp@4.0.x (stdio). The real tool set is
list-projects / get-spans / get-trace / ... (NOT the contract's draft names
phoenix_get_traces / phoenix_get_evaluations). We use `get-spans` filtered to our
project + the launchpilot reviewer/validation span names.

Everything here is best-effort: any failure returns None and logs, so a missing
or slow Phoenix MCP never breaks a run.
"""
from __future__ import annotations

import logging
import os

from app.config import get_settings
from app.contracts import ValidationIssueCode
from app.tools.mcp_bridge import McpBridge
from app import tracing

log = logging.getLogger("launchpilot.reflection")

_REVIEW_SPAN_NAMES = ["launchpilot.validation", "launchpilot.reviewer_gate"]
_ISSUE_TOKENS = [c.value for c in ValidationIssueCode]

_bridge: McpBridge | None = None


def _get_bridge() -> McpBridge:
    global _bridge
    if _bridge is None:
        s = get_settings()
        env = dict(os.environ)
        env["OTEL_SDK_DISABLED"] = "true"
        base = s.phoenix_endpoint or "https://app.phoenix.arize.com"
        _bridge = McpBridge(
            "npx",
            ["-y", "@arizeai/phoenix-mcp", "--baseUrl", base, "--apiKey", s.phoenix_api_key or ""],
        )
    return _bridge


def close() -> None:
    global _bridge
    if _bridge is not None:
        _bridge.close()
        _bridge = None


def _spans_text(result) -> str:
    parts = []
    for item in getattr(result, "content", None) or []:
        t = getattr(item, "text", None)
        if t:
            parts.append(t)
    return "\n".join(parts)


def summarize_failures(workspace_id: str | None = None, campaign_id: str | None = None) -> str | None:
    """Read past reviewer/validation spans from Phoenix MCP, summarize failures.

    Returns a concise advisory string (or None when disabled / nothing useful).
    Never raises -- reflection must not break the run.
    """
    s = get_settings()
    if not s.reflection_enabled:
        return None
    try:
        result = _get_bridge().call(
            "get-spans",
            {"project_identifier": s.phoenix_project, "names": _REVIEW_SPAN_NAMES, "limit": 100},
        )
        text = _spans_text(result)
    except Exception as exc:  # noqa: BLE001 - advisory only
        log.warning("reflection: get-spans failed: %s", exc)
        return None

    if not text:
        return None

    # Tally known issue-code tokens + explicit pass/fail markers from the spans.
    counts = {tok: text.count(tok) for tok in _ISSUE_TOKENS if tok in text}
    fails = text.count('"passed":false') + text.count("'passed': False")
    if not counts and not fails:
        summary = "과거 검수 스팬에서 반복 실패 패턴 없음."
    else:
        top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:3]
        freq = ", ".join(f"{k} x{v}" for k, v in top) or "(코드 미상)"
        summary = f"과거 검수 실패 {fails}건, 빈도 상위 이슈: {freq}. (참고용, 결정론 검수 우선)"

    # EVALUATOR span so the reflection shows in the trace (contract 06 §Reflection).
    with tracing.evaluator_span(
        "launchpilot.reflection.failure_pattern_summary",
        output_value={"summary": summary, "issue_counts": counts, "fail_count": fails},
        metadata={"workspace_id": workspace_id, "campaign_id": campaign_id,
                  "reflection_summary": summary},
        workspace_id=workspace_id,
        campaign_id=campaign_id,
    ):
        pass
    return summary
