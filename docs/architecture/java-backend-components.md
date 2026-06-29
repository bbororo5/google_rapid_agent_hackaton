# Java Backend Component Boundaries

This document fixes the internal component boundaries of the Java backend.
It is the working contract for later interface design and component-by-component
refactoring.

## Container Role

The Java backend is the deterministic product gateway.

It owns:

- frontend-facing HTTP and WebSocket contracts
- conversation command routing
- approval gates and approved business writes
- Elastic business persistence
- the Java side of service-level observability
- the bridge to Python Agent Core

It does not own:

- LLM reasoning
- agent worker orchestration
- evidence search policy
- runtime-only agent state
- Phoenix/OpenInference agent trace detail

Those belong to Python Agent Core.

## Components

| Component | Package | Responsibility | Inbound interface | Outbound dependencies |
| --- | --- | --- | --- | --- |
| API Adapter | `api` | HTTP controllers and API error mapping | Spring MVC routes | `importing` |
| WebSocket Adapter | `websocket` | Frontend stream transport, session registry, malformed frame handling | Spring WebSocket handler | `conversation`, `agentbridge`, `observability` |
| Conversation Application | `conversation` | Thread command routing, deterministic approval routing, timeline publication, Python stream relay | `ConversationCommandUseCase`, `ConversationConnectionUseCase`, `ConversationMessagePublisher` | `agentbridge`, `approval`, `observability` |
| Agent Bridge | `agentbridge` | Java-to-Python Agent Core REST/WS boundary and trace propagation | `AgentTurnPort`, `AgentStreamPort` | Python Agent Core contracts, `observability` |
| Importing Application | `importing` | CSV import use case and CSV parsing | `ImportUseCase` | Elastic persistence ports, `observability` |
| Approval Application | `approval` | Deterministic approval commit use case | `ApprovalUseCase` | Elastic persistence ports, `observability` |
| Elastic Persistence | `persistence.elastic` | Concrete Elastic adapters and index bootstrap | Repository interfaces consumed by application components | Elasticsearch client, `observability` |
| Observability | `observability` | Component-boundary events, correlation, downstream trace context | `ObservabilityGateway` | logging now; OpenTelemetry or Google Cloud exporter later |
| Contracts | `contracts.*` | Java records mirroring external contracts | Data records only | none |
| Common | `common` | Small shared utilities and cross-cutting exceptions | Utility classes | none |
| Config | `config` | Spring wiring and runtime configuration | Spring configuration | component beans |

## Naming Rule: No Java `agentcore` Component

`Agent Core` means the separate Python container.

Inside Java, the component that talks to that container is named
`agentbridge`. This avoids implying that Java owns agent reasoning or worker
orchestration. Java only submits turns, subscribes to safe stream blocks, and
propagates correlation context.

## Dependency Direction

The intended direction is:

```text
api / websocket
  -> conversation / importing
  -> approval / agentbridge / persistence ports
  -> persistence.elastic / external Python

all business components
  -> observability
```

Rules:

- Adapters call application interfaces, not concrete application internals.
- Application components depend on ports and contracts, not transport handlers.
- `agentbridge` depends on Java-Python contracts, but Python Agent Core remains
  outside the Java container.
- `persistence.elastic` is the only Java component that should know Elastic
  client details.
- `observability` is a side boundary. Business components may call
  `ObservabilityGateway`, but must not call logging, OpenTelemetry, or Google
  Cloud APIs directly for service-level signals.
- `contracts.*` packages contain records and enums only. They must not depend on
  application services.
- `common` must stay small. If a class carries business meaning, it belongs to a
  business component, not `common`.

## Main Scenarios

### CSV Import

```text
Frontend
  -> api.ImportController
  -> importing.ImportUseCase
  -> persistence.elastic content post repository
  -> Elasticsearch
```

Observability is emitted at the import use case boundary and the Elastic adapter
boundary.

### Free-Form User Turn

```text
Frontend
  -> websocket.AgentStreamHandler
  -> conversation.ConversationCommandUseCase
  -> agentbridge.AgentTurnPort
  -> Python Agent Core
```

The conversation component decides whether the command is deterministic Java
work or a free-form agent turn. Free-form content goes to Python Agent Core
through `agentbridge`.

### Agent Stream Relay

```text
Python Agent Core
  -> agentbridge.AgentStreamPort
  -> conversation.ConversationMessagePublisher
  -> websocket frontend sessions
```

Java treats Python output as safe product blocks, records them in the thread
timeline, assigns the frontend-facing stream shape, and broadcasts them.

### Approval Commit

```text
Frontend approval action
  -> websocket.AgentStreamHandler
  -> conversation.ConversationCommandUseCase
  -> approval.ApprovalUseCase
  -> persistence.elastic approval repositories
  -> Elasticsearch
```

Approval persistence is deterministic Java work. Python may help interpret or
revise drafts before approval, but approved `growth_briefs` and
`calendar_events` are written by Java.

## Refactoring Checkpoints

Each later refactor should leave these statements true:

- The public frontend contract remains `message.send` in and `StreamMessage`
  blocks out.
- The Java-Python boundary remains `POST /internal/agent/turns` plus the
  internal agent stream WebSocket.
- Java approval commits do not call Python.
- Python Agent Core does not write approved business documents.
- Component observability goes through `ObservabilityGateway`.
- Package names reflect component responsibility, not incidental technology or
  temporary implementation detail.
