# LaunchPilot Backend

Java 21 / Spring Boot gateway for LaunchPilot.

The backend owns business persistence and the frontend-facing stream. The agent core owns contextual reasoning.

## Public Contract

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/import/csv` | Ingest CSV rows into `content_posts` and create the thread routing context. |
| `WS` | `/api/agent/threads/{threadId}/stream` | Conversation stream. Client sends `message.send`; server sends `StreamMessage.blocks[]`. |

There is no public agent run REST API. Agent conversation is carried over the WebSocket as `message.send`.

## Internal Contract

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/internal/agent/turns` | Forward a user turn to Python Agent Core. |
| `WS` | `/internal/agent/threads/{threadId}/stream` | Subscribe to Agent Core stream blocks and relay them to the frontend. |

## Build

```sh
sh ./gradlew test
sh ./gradlew bootRun
```

## Environment

| Variable | Purpose | Default |
| --- | --- | --- |
| `ELASTIC_URL` | Elasticsearch endpoint | `http://localhost:9200` |
| `ELASTIC_API_KEY` | Elastic API key | Optional; blank for local compose |
| `AGENT_SERVICE_URL` | Python Agent Core base URL | `http://localhost:8000` |

## Persistence Rule

Java writes Elastic only on CSV import and human approval. Agent-generated candidates stay conversational until approval.
