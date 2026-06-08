"""Elastic evidence via the Elasticsearch MCP Server using ES|QL (contract 04, method B).

Wrapper-in-front: the LaunchPilot domain tools open an MCP session and call the
server's `esql_query` tool with FIXED, wrapper-built ES|QL (never LLM-authored) +
positional `?` params, then normalize the result. The ADK workers never see raw
ES|QL or the MCP transport (contract 04 line 22 / line 222).

Why ES|QL instead of `search`: aggregation/filtering/projection run server-side,
so we no longer pull ~500 full docs and parse free-form per-doc text. ES|QL output
is a fixed-column ASCII table -> deterministic parsing.

Verified against @tocharianou/elasticsearch-mcp@0.8.0 (stdio): exposes esql_query
(+ es_search, list_indices, ...). esql_query input {query, params?}, output =
TextContent blocks: a summary line then a `| col | col |` table. The official
@elastic/mcp-server-elasticsearch (npm latest 0.3.1) has NO esql, hence this pkg.

Baseline math is delegated to es_client.compute_baseline so the MCP and direct-ES
paths stay semantically identical (recency split over the channel's posts). ES|QL
just does the filter+projection; Python does the split.

The server is spawned once via McpBridge (npx) and reused. ES creds come from the
same ELASTIC_URL/ELASTIC_API_KEY the direct-ES path uses.
"""
from __future__ import annotations

import logging
import os
import re

from app.config import get_settings
from app.tools import es_client
from app.tools.mcp_bridge import McpBridge

log = logging.getLogger("launchpilot.mcp")

_CONTENT_POSTS = "content_posts"
_TEAM_NOTES = "team_notes"

# ES|QL field/identifier safety: metric names and channels are injected into the
# query string (params only bind values, not identifiers), so allow-list them.
_IDENT = re.compile(r"^[A-Za-z0-9_]+$")

_bridge: McpBridge | None = None


def _get_bridge() -> McpBridge:
    global _bridge
    if _bridge is None:
        s = get_settings()
        env = dict(os.environ)
        # The Elasticsearch MCP server reads ES_URL + ES_API_KEY.
        env["ES_URL"] = s.elastic_url or ""
        env["ES_API_KEY"] = s.elastic_api_key or ""
        # Silence telemetry banners that would pollute the JSON-RPC stdout.
        env["OTEL_SDK_DISABLED"] = "true"
        _bridge = McpBridge("npx", ["-y", s.elastic_mcp_package], env=env)
    return _bridge


def close() -> None:
    global _bridge
    if _bridge is not None:
        _bridge.close()
        _bridge = None


def _err(tool_name: str, code: str, message: str, retryable: bool = False) -> dict:
    return {
        "ok": False,
        "tool_name": tool_name,
        "mcp_tool": "esql",
        "error": {"code": code, "message": message, "retryable": retryable},
        "duration_ms": 0,
    }


def _safe_ident(name: str) -> str:
    if not _IDENT.match(name or ""):
        raise ValueError(f"unsafe identifier for ES|QL: {name!r}")
    return name


def _parse_table(result) -> list[dict]:
    """Parse esql_query output (a `| col | col |` ASCII table) into row dicts."""
    text = "\n".join(getattr(i, "text", "") or "" for i in (getattr(result, "content", None) or []))
    header: list[str] | None = None
    rows: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):  # skip summary + separator (+---+) lines
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if header is None:
            header = cells
        else:
            rows.append(dict(zip(header, cells)))
    return rows


def _esql(query: str, params: list | None = None) -> list[dict]:
    """Run esql_query and return parsed rows. Raises on transport/query failure."""
    args = {"query": query}
    if params:
        args["params"] = params
    result = _get_bridge().call("esql_query", args)
    if getattr(result, "isError", False):
        raise RuntimeError(f"ES|QL error: {getattr(result, 'content', '')}")
    return _parse_table(result)


def _tenancy_clauses(workspace_id, campaign_id, since):
    """Build value-bound ES|QL predicates + ordered params (None -> omitted).

    Tenancy/date are bound as positional `?` params (values, never identifiers),
    so no allow-listing is needed for them.
    """
    clauses: list[str] = []
    params: list = []
    if campaign_id is not None:
        clauses.append("campaign_id == ?")
        params.append(campaign_id)
    if workspace_id is not None:
        clauses.append("workspace_id == ?")
        params.append(workspace_id)
    if since is not None:
        clauses.append("published_at >= ?")
        params.append(since)
    return clauses, params


def query_metric_baseline(metric_name: str, channel: str, scope=None) -> dict:
    ws, camp, cur_start, cur_end, base_start, base_end = es_client._scope_parts(scope)
    m = _safe_ident(metric_name)
    field = f"metrics.{m}"
    # Filter + project server-side; precise window split done in Python (shared).
    tclauses, tparams = _tenancy_clauses(ws, camp, base_start)
    where = " AND ".join([f"channel == ?", f"{field} IS NOT NULL", *tclauses])
    query = f"FROM {_CONTENT_POSTS} | WHERE {where} | KEEP post_id, published_at, {field}"
    rows = _esql(query, [channel, *tparams])
    # Reshape ES|QL rows into the post-dict shape es_client.compute_baseline expects.
    posts = []
    for r in rows:
        val = r.get(field)
        if val in (None, "", "null"):
            continue
        posts.append({
            "post_id": r.get("post_id"),
            "channel": channel,
            "published_at": r.get("published_at"),
            "metrics": {m: float(val)},
        })
    return es_client.compute_baseline(posts, m, channel,
                                      cur_start, cur_end, base_start, base_end)


def search_content_posts(channels: list[str], metric_name: str, scope=None) -> dict:
    ws, camp, _cs, _ce, base_start, _be = es_client._scope_parts(scope)
    m = _safe_ident(metric_name)
    field = f"metrics.{m}"
    chans = ", ".join(f'"{_safe_ident(c)}"' for c in channels) if channels else None
    tclauses, tparams = _tenancy_clauses(ws, camp, base_start)
    parts = [f"{field} IS NOT NULL", *tclauses]
    if chans:
        parts.append(f"channel IN ({chans})")  # allow-listed identifiers, safe
    query = (
        f"FROM {_CONTENT_POSTS} | WHERE {' AND '.join(parts)} | SORT {field} DESC "
        f"| KEEP post_id | LIMIT 5"
    )
    rows = _esql(query, tparams or None)
    refs = [r.get("post_id") for r in rows if r.get("post_id")]
    if not refs:
        return _err("search_content_posts", "NO_EVIDENCE_FOUND", f"no {m} posts on {channels}")
    return {"ok": True, "tool_name": "search_content_posts", "mcp_tool": "esql",
            "evidence_refs": refs, "duration_ms": 0}


def search_team_notes(query: str, scope=None) -> dict:
    # team_notes is optional (contract 04). ES|QL has no full-text scoring; pull a
    # few note ids best-effort. NOTE: the team_notes index does not carry
    # workspace_id/campaign_id columns (unlike content_posts), so we must NOT add
    # tenancy predicates here or ES|QL rejects the query (Unknown column ...).
    rows = _esql(f"FROM {_TEAM_NOTES} | KEEP note_id | LIMIT 5")
    refs = [r.get("note_id") for r in rows if r.get("note_id")]
    if not refs:
        return _err("search_team_notes", "NO_EVIDENCE_FOUND", "no team notes")
    return {"ok": True, "tool_name": "search_team_notes", "mcp_tool": "esql",
            "evidence_refs": refs, "duration_ms": 0}


def load_growth_brief_context(parent_brief_id: str) -> dict:
    # Continuity (R12/R13) not implemented; return empty context rather than fail.
    return {"ok": True, "tool_name": "load_growth_brief_context", "mcp_tool": "esql",
            "evidence_refs": [], "brief": None, "duration_ms": 0}
