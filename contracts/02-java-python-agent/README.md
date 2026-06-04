# LaunchPilot Java-Python Agent Core Contract

Status: Current v1.0  
Boundary: Java Spring Boot Backend <-> Python Agent Core

## Purpose

This contract defines the internal boundary for conversation-first agent work.
Java forwards user turns and thread context to Agent Core. Agent Core interprets
the turn, chooses tools/workers, and streams user-safe message blocks back to Java.

## Contract Shape

- Java sends user turns with `POST /internal/agent/turns`.
- Python streams output over `WS /internal/agent/threads/{thread_id}/stream`.
- The internal stream uses the same block vocabulary as the frontend-facing stream:
  `text`, `activity`, `markdown_document`, `artifact`, `approval`, `result`, `error`.
- Java remains the owner of approval validation and immutable writes.
- Python must not send raw chain-of-thought, raw Gemini chunks, provider-private fields, raw MCP transport frames, or private prompts.

## Responsibilities

Java owns:

- thread id and public timeline persistence,
- CSV ingestion and Elastic writes,
- final approval validation,
- `growth_briefs` and `calendar_events` append-only persistence,
- normalization into frontend `StreamMessage`.

Python Agent Core owns:

- free-form user intent interpretation,
- context gathering,
- worker/tool selection,
- evidence search through wrapper tools,
- hypothesis and experiment drafting,
- user-safe block output.

## Internal Turn

`POST /internal/agent/turns`

```json
{
  "thread_id": "thread_20260601_001",
  "workspace_id": "demo_workspace",
  "campaign_id": "camp_comeback_teaser",
  "content": "이 CSV 보고 리텐션 중심으로 봐줘.",
  "attachments": [
    {
      "kind": "csv_import",
      "id": "imp_20260601_001"
    }
  ],
  "client_created_at": "2026-06-01T16:31:00+09:00",
  "trace_context": {
    "request_id": "req_20260601_001",
    "source": "java-backend",
    "otel_trace_id": null
  }
}
```

## Internal Stream

`WS /internal/agent/threads/{thread_id}/stream`

Python emits user-safe block messages in the order Java should expose them.
Java may persist them as-is or normalize them into frontend `StreamMessage`.

```json
{
  "id": "msg_agent_001",
  "thread_id": "thread_20260601_001",
  "sequence": 4,
  "role": "assistant",
  "created_at": "2026-06-01T16:31:10+09:00",
  "blocks": [
    { "kind": "activity", "title": "Checked metric baseline", "status": "done" },
    { "kind": "text", "text": "The save-rate lift looks repeatable." }
  ]
}
```
