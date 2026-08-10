# Memory And DB Flow

LaunchPilot keeps conversation, reasoning memory, business data, and traces separate.

## Layers

| Layer | Owner | Lifetime | Purpose |
| --- | --- | --- | --- |
| Agent working memory | Python Agent Core | While handling the conversation turn | Intermediate signals, hypotheses, drafts, reviewer notes. |
| Thread timeline | Java Backend | Conversation session | User/assistant messages, sequence numbers, approval gates, approval receipts. |
| Business data | Elastic | Permanent | Imported posts and approved immutable outputs. |
| Observability | Phoenix/Arize | Permanent | Agent traces and evaluation signals. Not final evidence. |

## Write Rules

Java writes Elastic only at two product moments:

1. CSV import writes `content_posts`.
2. Human approval writes `growth_briefs` and `calendar_events`.

Agent Core reads evidence and produces candidate blocks, but it does not persist business documents.

## Conversation Flow

```text
1. User uploads CSV.
2. Java indexes content_posts and records the thread's workspace/campaign context.
3. User continues in free conversation through message.send.
4. Java stores the user message and forwards the turn to Agent Core.
5. Agent Core streams blocks such as text, activity, artifact, markdown_document, approval, result, or error.
6. Java wraps those blocks as StreamMessage and broadcasts them to the frontend.
7. The UI reacts to block kind. Approval blocks open the right panel and show approval controls.
8. Approval, whether from a button or natural-language confirmation interpreted by Agent Core, returns through message.send.
9. Java persists approved outputs only after an approval target is resolved.
```

## Invariants

- Frontend state is not Agent Core memory.
- Agent working memory is not persistent business data.
- Observability traces are useful for debugging and evaluation, but are not customer-facing evidence.
- Pre-approval candidates remain conversational artifacts until approval.
