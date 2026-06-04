# Backend Design

Status: current conversation-first design.

## Boundary

Frontend and Java share one public agent channel:

```text
WS /api/agent/threads/{threadId}/stream
```

The client sends only `message.send` for agent conversation. Java returns one message shape:

```text
StreamMessage {
  id,
  threadId,
  sequence,
  role,
  createdAt,
  blocks[]
}
```

The UI decides what to render from each block `kind`, not from transport-specific event names.

## Responsibilities

| Layer | Owns |
| --- | --- |
| Frontend | Free conversation UI, output panel list/detail rendering, inline review/approval cards, local candidate editing before approval. |
| Java | Public WebSocket, message timeline, approval gate, CSV import, Elastic writes. |
| Python Agent Core | Contextual interpretation, tool use, reasoning, markdown/artifact/approval/result block production. |
| Elastic | Imported content and approved immutable outputs. |

## Flow

```text
1. Frontend uploads CSV with POST /api/import/csv.
2. Java indexes content_posts and records thread workspace/campaign context.
3. Frontend opens WS /api/agent/threads/{threadId}/stream.
4. User sends natural language through message.send.
5. Java records the user message and forwards the turn to Python Agent Core.
6. Python streams blocks back to Java.
7. Java wraps blocks as StreamMessage and broadcasts them to the thread.
8. If an approval block appears, the UI may show buttons. Button clicks still send message.send with an optional action hint.
9. Java persists growth_briefs and calendar_events only after approval.
```

## Block Kinds

| Kind | UI reaction |
| --- | --- |
| `text` | Render as normal assistant conversation. |
| `activity` | Update lightweight progress/status. |
| `markdown_document` | Add a small document card to the thread and open the right panel with the document. |
| `artifact` | Show generated structured output as an inline review card and save accepted output in the right panel. |
| `approval` | Show approval/reject/request-change controls as an inline gate. |
| `result` | Show completion or receipt state and save the approved output in the right panel. |
| `error` | Show recoverable error state. |

## Non-Goals

The frontend does not manage agent internals, replay commands, or Python state. Those are implementation details behind the conversation stream.
