# LaunchPilot Evidence Tool Contract

Status: Draft v0.1  
Boundary: Python Agent Service / Google ADK <-> Elasticsearch MCP Server <-> Elastic Cloud Serverless  
Last updated: 2026-06-01

## Purpose

This contract defines how the Google ADK-based Python Agent retrieves evidence from Elastic.

LaunchPilot does not use Google Cloud Agent Builder or Elastic Agent Builder for this layer. The Python Agent uses Google ADK and calls the Elasticsearch MCP Server through a small LaunchPilot domain wrapper.

## Tooling Layers

The contract has two distinct tool layers:

| Layer | Owner | Tool names | Purpose |
| --- | --- | --- | --- |
| Elasticsearch MCP Server | Elastic MCP server | `list_indices`, `get_mappings`, `search`, `esql`, `get_shards` | Generic Elasticsearch access exposed through MCP. |
| LaunchPilot Evidence Wrapper | Python Agent Service | `search_content_posts`, `query_metric_baseline`, `search_team_notes`, `load_growth_brief_context` | Domain-safe tools used by ADK workers. |

The ADK workers should call the LaunchPilot wrapper tools, not raw MCP tools directly. The wrapper is responsible for constructing safe Elasticsearch DSL or ES|QL, limiting indices, and normalizing results into evidence objects.

Official reference checked during contract design:

- Elasticsearch MCP Server available tools: `list_indices`, `get_mappings`, `search`, `esql`, `get_shards`.
- Elasticsearch MCP Server is the appropriate branch for a custom Google ADK agent that does not use Agent Builder.

## Allowed MCP Tool Usage

| Wrapper tool | Underlying MCP tool | Allowed indices | Notes |
| --- | --- | --- | --- |
| `search_content_posts` | `search` | `content_posts` | Finds source posts and metric rows for evidence. |
| `query_metric_baseline` | `esql` | `content_posts` | Computes current/baseline metric aggregates. |
| `search_team_notes` | `search` | `team_notes` | Optional v0.1 qualitative search; index contract is not finalized yet. |
| `load_growth_brief_context` | `search` or `get_mappings` + `search` | `growth_briefs` | Loads an approved prior brief for `parent_brief_id` restoration. **Caller: Central Orchestrator only (session-start pre-injection), not the ADK workers.** |

Raw MCP tools that inspect cluster metadata, such as `list_indices` and `get_mappings`, are allowed only during startup validation or diagnostics. They should not be used as part of normal reasoning unless the wrapper needs to verify index shape.

> Caller ownership: `search_content_posts` / `query_metric_baseline` are called by the Data Analyst worker, `search_team_notes` by the Data Strategist worker, and `load_growth_brief_context` by the **Central Orchestrator** once at session start when `parent_brief_id` is present (it pre-injects the prior context into Shared Context; workers then read from memory, not the tool). See `docs/agent-tool-spec.md`.

## Common Request Fields

All wrapper requests include:

- `agent_run_id`: Current Java-generated agent run ID.
- `workspace_id`: Workspace scope.
- `campaign_id`: Campaign scope.

All time filters use ISO date strings or ISO datetime strings.

## Common Response Shape

Every wrapper response returns:

- `ok`
- `tool_name`
- `mcp_tool`
- `evidence_refs`
- `duration_ms`

`evidence_refs[].ref_id` is the only field that should be copied into final `signals[].evidence_refs`, `hypotheses[].supporting_evidence_refs`, and `growth_briefs.source_evidence_refs`.

## EvidenceRef

`EvidenceRef` is the normalized evidence unit passed to Gemini context.

```json
{
  "ref_id": "post_014",
  "ref_type": "content_post",
  "source_index": "content_posts",
  "title": "Practice room BTS clip",
  "summary": "TikTok BTS clip with save_rate 0.074, 2.8x above baseline.",
  "timestamp": "2026-05-27T20:00:00+09:00",
  "score": 0.92,
  "metrics": {
    "save_rate": 0.074,
    "views": 120000
  }
}
```

Allowed `ref_type` values:

- `content_post`
- `metric_aggregate`
- `team_note`
- `growth_brief`

## Wrapper Tool: `search_content_posts`

Purpose: retrieve high-signal content posts from `content_posts`.

Underlying MCP tool: `search`

Request:

```json
{
  "agent_run_id": "run_20260601_001",
  "workspace_id": "demo_workspace",
  "campaign_id": "camp_comeback_teaser",
  "date_range": {
    "start": "2026-05-25",
    "end": "2026-06-01"
  },
  "channels": ["tiktok", "instagram"],
  "query": "behind the scenes practice clips",
  "metric_filters": [
    {
      "metric_name": "save_rate",
      "operator": "gte",
      "value": 0.05
    }
  ],
  "limit": 10
}
```

Response:

```json
{
  "ok": true,
  "tool_name": "search_content_posts",
  "mcp_tool": "search",
  "evidence_refs": [],
  "duration_ms": 180
}
```

## Wrapper Tool: `query_metric_baseline`

Purpose: compute current and baseline metric aggregates over `content_posts`.

Underlying MCP tool: `esql`

This replaces the narrower Gemini draft name `query_follower_growth`. The tool is intentionally metric-agnostic so it can handle `save_rate`, `engagement_rate`, `views`, `follower_count`, or other numeric metrics.

Request:

```json
{
  "agent_run_id": "run_20260601_001",
  "workspace_id": "demo_workspace",
  "campaign_id": "camp_comeback_teaser",
  "metric_name": "save_rate",
  "channel": "tiktok",
  "current_window": {
    "start": "2026-05-25",
    "end": "2026-06-01"
  },
  "baseline_window": {
    "start": "2026-04-25",
    "end": "2026-05-24"
  }
}
```

Response:

```json
{
  "ok": true,
  "tool_name": "query_metric_baseline",
  "mcp_tool": "esql",
  "metric_name": "save_rate",
  "current_value": 0.074,
  "baseline_value": 0.026,
  "lift_ratio": 2.8,
  "evidence_refs": [],
  "duration_ms": 142
}
```

## Wrapper Tool: `search_team_notes`

Purpose: retrieve qualitative context from team notes.

Underlying MCP tool: `search`

The `team_notes` index is optional in v0.1. If unavailable, the wrapper must return `ok: false` with `code: INDEX_UNAVAILABLE` rather than hallucinating note evidence.

## Wrapper Tool: `load_growth_brief_context`

Purpose: restore previous approved context when Java passes `parent_brief_id`.

Underlying MCP tool: `search`

This tool reads `growth_briefs` only. It must not read pending agent state because pending candidate state is intentionally frontend-local before approval.

## Error Shape

```json
{
  "ok": false,
  "tool_name": "search_team_notes",
  "mcp_tool": "search",
  "error": {
    "code": "INDEX_UNAVAILABLE",
    "message": "team_notes index is not available in this environment.",
    "retryable": false
  },
  "duration_ms": 12
}
```

Recommended error codes:

- `INVALID_TOOL_REQUEST`
- `MCP_TOOL_FAILED`
- `INDEX_UNAVAILABLE`
- `ESQL_FAILED`
- `SEARCH_FAILED`
- `NO_EVIDENCE_FOUND`

## Final Payload Rules

- `signals[].evidence_refs` may include `content_post`, `metric_aggregate`, and `team_note` refs.
- `hypotheses[].supporting_evidence_refs` may include `content_post`, `team_note`, and `growth_brief` refs.
- The final payload must never include raw Elasticsearch query DSL, ES|QL strings, credentials, or raw MCP transport messages.
- The final payload should include only stable `ref_id` strings and human-readable summaries already incorporated into the signal/hypothesis text.

## Open Decisions

- Whether `team_notes` gets a Java-owned document contract or remains demo seed data.
- Whether to expose raw MCP request/response in debug logs for the hackathon demo.
- Whether to add a dedicated `metric_aggregates` index later or keep aggregate evidence virtual.
