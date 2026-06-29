# Java Backend Observability

The Java backend exposes observability through one internal component:
`com.launchpilot.observability`.

Business components do not call OpenTelemetry, Google Cloud APIs, or logging
frameworks directly for service-level signals. They call `ObservabilityGateway`
at component boundaries.

## Current Runtime Path

The current implementation is `LoggingObservabilityGateway`.

It records:

- operation start/success/failure logs for CSV import, conversation command
  handling, Python agent turn submit, agent stream relay, approval persistence,
  and Elastic read/write adapters
- WebSocket session open/close/reject and parse-failure events
- MDC correlation fields on Java logs:
  `request_id`, `trace_id`, `thread_id`, `workspace_id`, `campaign_id`,
  `component`, `operation`
- downstream correlation headers for Python Agent Core:
  `x-launchpilot-request-id`, `x-launchpilot-trace-id`,
  `x-launchpilot-thread-id`, `x-launchpilot-workspace-id`,
  `x-launchpilot-campaign-id`, plus W3C `traceparent`
- `trace_context` in the Java -> Python turn request body

On Google Cloud runtimes, stdout/stderr logs are collected by Cloud Logging.
The configured console log pattern includes the correlation fields above, so
Cloud Logging queries can group Java events by `trace_id`, `thread_id`, or
component operation.

## Component Boundaries

Observed Java boundaries:

| Component | Boundary |
| --- | --- |
| `api`/`websocket` | WebSocket session and malformed message events |
| `conversation` | frontend command handling and Python stream relay |
| `importing` | CSV import use case |
| `agentbridge` | Java -> Python turn submission and trace propagation |
| `approval` | deterministic approval persistence use case |
| `persistence.elastic` | Elastic read/write adapter operations |

## Google Cloud Operations Upgrade Path

The interface is intentionally stable:

```java
ObservabilityGateway
ObservationScope
DownstreamTraceContext
```

To move from log-based observability to full OpenTelemetry export, add a new
adapter inside `observability` that implements `ObservabilityGateway` and emits
OpenTelemetry spans/metrics/log attributes. Existing business components should
not change.

The expected production route is:

```text
Java components
  -> ObservabilityGateway
  -> OpenTelemetry SDK or Java agent
  -> OTLP / Google exporter / Collector
  -> Google Cloud Operations
```

Python Agent Core should continue receiving the downstream correlation payload
from Java so both containers can be queried together by the same `trace_id` and
`thread_id`.
