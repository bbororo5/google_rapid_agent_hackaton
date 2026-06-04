"""Real Elastic MCP wiring (next step — not on the golden path).

When ELASTIC_MCP_URL is set, the evidence wrapper should construct safe ES|QL /
DSL and call the Elasticsearch MCP server's generic tools (esql/search) via an
MCP client session, then normalize results into the same evidence dicts the stub
returns. This is intentionally a stub-raising placeholder so the contract-
enforced golden path runs offline; flip it on once a cluster + MCP server exist.

ADK side (alternative wiring): expose the MCP server to the agent directly with
  from google.adk.tools.mcp_tool import McpToolset
  from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
  McpToolset(connection_params=StreamableHTTPConnectionParams(url=ELASTIC_MCP_URL))
but contract 04 requires the LaunchPilot wrapper in front, so prefer wiring the
MCP session inside these functions and keeping the wrapper as the agent's tool.
"""
from __future__ import annotations


def _not_implemented(name: str) -> dict:
    raise NotImplementedError(
        f"{name}: real Elastic MCP path not implemented. "
        "Unset ELASTIC_MCP_URL to use seeded stub evidence, or implement the "
        "MCP session call here."
    )


def query_metric_baseline(metric_name: str, channel: str) -> dict:
    return _not_implemented("query_metric_baseline")


def search_content_posts(channels: list[str], metric_name: str) -> dict:
    return _not_implemented("search_content_posts")


def search_team_notes(query: str) -> dict:
    return _not_implemented("search_team_notes")


def load_growth_brief_context(parent_brief_id: str) -> dict:
    return _not_implemented("load_growth_brief_context")
