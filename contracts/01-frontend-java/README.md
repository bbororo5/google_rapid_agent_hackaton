# LaunchPilot Frontend-Backend Contract

Status: Current v1.0  
Last updated: 2026-06-04

## Contract Principles

This contract describes the boundary between the Next.js frontend and the Java Spring Boot gateway.

- The product runtime is conversation-first.
- The frontend sends agent-facing user turns with one command: `message.send`.
- The backend sends one frame shape: `StreamMessage`.
- UI behavior comes from `StreamMessage.blocks[].kind`, not from separate workflow event names.
- WebSocket remains the live transport for delivery, ordering, reconnect, and client-side send queueing.
- Java owns persistence, sequence assignment, approval validation, and immutable business writes.
- Agent Core owns free-form intent interpretation, context gathering, tool choice, artifact drafting, and conversational response.
- The frontend never calls Python Agent Service, Gemini, Elastic, or Arize directly.
- Streamed reasoning must be user-safe: summaries, evidence references, tool/activity summaries, and structured artifacts only.

## Endpoint Summary

| Flow | Method | Path | Owner |
| --- | --- | --- | --- |
| CSV ingestion | `POST` | `/api/import/csv` | Java `ImportController` |
| Conversation stream | `WS` | `/api/agent/threads/{thread_id}/stream` | Java WebSocket gateway |

## CSV Ingestion

`POST /api/import/csv`

Purpose: upload SNS metric CSV data and index normalized rows into Elastic.

Request content type: `multipart/form-data`

Fields:

- `file`: CSV file. Required.
- `workspace_id`: Workspace key. Required.
- `campaign_id`: Campaign key. Required.
- `source_platform`: Optional source platform. Default: `unknown`.

Response: `201 Created`

```json
{
  "ok": true,
  "import_id": "imp_20260601_001",
  "workspace_id": "demo_workspace",
  "campaign_id": "camp_comeback_teaser",
  "indexed_count": 184,
  "failed_count": 0,
  "columns": ["post_id", "published_at", "channel", "views", "likes", "comments", "save_rate"],
  "created_at": "2026-06-01T16:30:10+09:00"
}
```

## Conversation Stream

`WS /api/agent/threads/{thread_id}/stream`

The client sends exactly one command shape:

```json
{
  "command_id": "cmd_20260601_001",
  "type": "message.send",
  "thread_id": "thread_20260601_001",
  "content": "좋아, 승인할게. 캘린더에 넣어줘.",
  "action": {
    "name": "approve",
    "target_id": "appr_20260601_001"
  },
  "client_created_at": "2026-06-01T16:33:10+09:00"
}
```

`content` is always the user-visible utterance sent to Agent Core. `action` is optional metadata attached to a UI-originated utterance; it is not a separate command path.

The server sends exactly one frame shape:

```json
{
  "id": "msg_20260601_001",
  "thread_id": "thread_20260601_001",
  "sequence": 12,
  "role": "assistant",
  "created_at": "2026-06-01T16:31:10+09:00",
  "blocks": [
    { "kind": "text", "text": "I found a repeatable save-rate signal." },
    { "kind": "activity", "title": "Checked metric baseline", "status": "done" },
    { "kind": "markdown_document", "id": "doc_evidence_scan_001", "title": "Evidence notes", "markdown": "## Evidence notes\n..." }
  ]
}
```

Supported block kinds:

- `text`: Natural-language chat content.
- `activity`: User-visible work progress.
- `markdown_document`: Markdown document to render as a small thread card and open in the right panel.
- `artifact`: Structured output such as a signal, hypothesis, experiment plan, or growth brief.
- `approval`: Approval surface before consequential persistence.
- `result`: Completed business result such as created brief/calendar references.
- `error`: User-visible error state.

## UI Mapping

- Store messages by message `id`; ignore duplicate message ids. Use `sequence` for ordering, not as the only dedupe guard, because conversation replies and replayed work blocks may interleave.
- Render a message by iterating through `blocks[]`.
- `markdown_document` opens the right panel immediately and also appears as a compact card in the thread.
- The right panel keeps an output list. Markdown documents, confirmed signals, experiment plans, and approval results can be saved as selectable output cards; selecting a card renders its markdown detail in the panel.
- Approval button clicks send `message.send` with natural-language `content` plus optional `action`.
- Free text such as "승인할게" is still just `message.send`; Agent Core interprets it in context.
- Java validates open approval targets and final drafts before writing `growth_briefs` or `calendar_events`.

## Examples

- `examples/agent-stream-message-frame.json`
- `examples/message-send-command.json`
