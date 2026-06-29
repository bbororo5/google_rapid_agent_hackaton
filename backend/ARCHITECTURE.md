# LaunchPilot Java Backend Component Architecture

Status: target refactor plan.

This document defines the Java container's internal component boundaries. The
boundaries follow the product message flow rather than the current technical
package layers.

## Container Role

The Java Backend is the public gateway and business persistence owner.

It does not perform agent reasoning. Python Agent Core owns interpretation,
state reduction, worker orchestration, tool use, and user-safe block generation.

The Java Backend owns:

- frontend-facing HTTP and WebSocket contracts
- CSV import into Elastic evidence documents
- frontend conversation timeline and replay
- Java-to-Python turn forwarding
- Python-to-frontend stream relay
- approval gate capture and deterministic approval actions
- immutable approved business writes to Elastic
- service-level observability for Java boundaries

## Container Messages

| Direction | Contract | Message | Java owner |
| --- | --- | --- | --- |
| Frontend -> Java | `contracts/01-frontend-java/openapi.yaml` | `POST /api/import/csv` | `importing` |
| Frontend -> Java | `contracts/01-frontend-java/asyncapi.yaml` | `message.send` | `conversation` |
| Java -> Python | `contracts/02-java-python-agent/openapi.yaml` | `InternalAgentTurn` | `agentbridge` |
| Python -> Java | `contracts/02-java-python-agent/asyncapi.yaml` | `InternalStreamMessage` | `agentbridge` |
| Java -> Elastic | `contracts/03-java-elastic/documents.schema.json` | `content_posts`, `campaigns` | `persistence.elastic` |
| Java -> Elastic | `contracts/03-java-elastic/documents.schema.json` | `growth_briefs`, `calendar_events` | `approval` + `persistence.elastic` |

## Target Packages

```text
com.launchpilot
├── api                  # public HTTP edge
├── websocket            # public WebSocket transport edge
├── conversation          # message.send orchestration and live thread runtime
├── importing             # CSV import use case
├── agentbridge           # Java <-> Python Agent Core boundary
├── approval              # deterministic approval use case
├── persistence.elastic   # Elastic repositories and index bootstrap
├── contracts             # Java records mirroring external contracts
├── observability         # Java service-level observability boundary
├── common                # cross-component errors, IDs, and small primitives
└── config
```

## Component Boundaries

## Dependency Rules

The Java Backend should depend inward from transport and adapters toward use
cases. Components communicate through explicit interfaces instead of reaching
across package internals.

Allowed dependency direction:

```text
api/websocket -> conversation/importing
conversation -> agentbridge ports, approval, conversation runtime ports
importing -> persistence.elastic ports, conversation ThreadContextStore
approval -> persistence.elastic ports, conversation ApprovalGateStore/ThreadContextStore
agentbridge -> contracts.agentbridge, observability
persistence.elastic -> contracts.elastic, Elastic client
observability -> no business component
all components -> common
config -> concrete adapters and implementations
```

Forbidden dependencies:

- `api` and `websocket` must not call `agentbridge` or `persistence.elastic`
  directly.
- `conversation` must not depend on concrete Python or Elastic adapter classes.
- `agentbridge` must not call `approval`, `importing`, or `conversation` use
  cases.
- `approval` must not call Python Agent Core.
- `persistence.elastic` must not know frontend or Python transport messages.
- `observability` must not own business decisions or product workflow.
- `common` must not call business components or transport adapters.

## Interface Ownership

Each interface belongs to the component that defines the business need, not the
adapter that happens to satisfy it.

| Interface | Owner | Implemented by | Reason |
| --- | --- | --- | --- |
| `ConversationCommandUseCase` | `conversation` | `conversation` | WebSocket edge sends frontend commands into the conversation use case. |
| `ConversationTimeline` | `conversation` | `conversation` | Timeline is Java live conversation runtime, not transport. |
| `ThreadContextStore` | `conversation` | `conversation` | Workspace/campaign routing context is owned by live conversation runtime. |
| `ApprovalGateStore` | `conversation` | `conversation` | Approval blocks are captured from stream state before approval use case runs. |
| `ImportUseCase` | `importing` | `importing` | HTTP import edge calls one import use case. |
| `AgentTurnPort` | `conversation` | `agentbridge` | Conversation needs to submit free-form turns without knowing Python transport. |
| `AgentStreamPort` | `conversation` | `agentbridge` | Conversation needs Python stream events without knowing WS client details. |
| `ApprovalUseCase` | `approval` | `approval` | Conversation delegates deterministic approval action handling. |
| `CampaignRepository` | `importing` | `persistence.elastic` | Importing needs to upsert campaign context. |
| `ContentPostRepository` | `importing` | `persistence.elastic` | Importing needs to persist imported evidence rows. |
| `ApprovalDocumentRepository` | `approval` | `persistence.elastic` | Approval needs idempotency and immutable business writes. |

## Component Interface Summary

| Component | Inbound interfaces | Outbound interfaces |
| --- | --- | --- |
| `api` | HTTP controllers | `ImportUseCase` |
| `websocket` | `WebSocketHandler` | `ConversationCommandUseCase`, session broadcaster |
| `conversation` | `ConversationCommandUseCase`, `AgentStreamListener` | `AgentTurnPort`, `AgentStreamPort`, `ApprovalUseCase` |
| `importing` | `ImportUseCase` | `CampaignRepository`, `ContentPostRepository`, `ThreadContextStore` |
| `agentbridge` | `AgentTurnPort`, `AgentStreamPort` | Python REST/WS contracts |
| `approval` | `ApprovalUseCase` | `ApprovalGateStore`, `ThreadContextStore`, `ApprovalDocumentRepository` |
| `persistence.elastic` | repository interfaces | Elastic Java client |
| `observability` | `ObservabilityGateway` | logging, metrics, tracing backends |

### `api`

Transport-only HTTP edge.

Responsibilities:

- parse HTTP requests
- perform endpoint-level validation
- call a use case
- translate exceptions into contract error responses

It must not call Python Agent Core or Elastic directly.

### `websocket`

Transport-only WebSocket edge.

Responsibilities:

- extract and validate `thread_id` from the WebSocket path
- parse frontend `message.send`
- register/unregister WebSocket sessions
- call `conversation`
- send already-built `StreamMessage` objects to frontend sessions

It must not decide approval semantics, build Python requests, or persist
business documents.

### `conversation`

Frontend conversation orchestration.

Responsibilities:

- own the `message.send` use case
- append user and assistant/system messages to the thread timeline
- guard duplicate frontend commands
- resolve or create live thread workspace/campaign context
- route free-form turns to `agentbridge`
- route deterministic actions to `approval`
- capture approval gates from Python stream blocks
- build frontend-safe result/error/text blocks

It should depend on ports, not concrete Python or Elastic clients.

Candidate public interfaces:

```java
public interface ConversationCommandUseCase {
    void handle(ClientCommandEnvelope command);
}

public interface ConversationTimeline {
    StreamMessage append(String threadId, String role, List<Map<String, Object>> blocks);
    List<StreamMessage> history(String threadId);
}

public interface ThreadContextStore {
    RunContext resolveOrCreate(String threadId);
    void register(String threadId, RunContext context);
}

public interface ApprovalGateStore {
    Optional<ApprovalGateRequest> get(String threadId);
    void captureIfPresent(String threadId, List<Map<String, Object>> blocks);
    void remove(String threadId);
}
```

### `importing`

CSV import use case.

Responsibilities:

- parse uploaded CSV rows
- normalize rows into content post documents
- create or update campaign working context
- register the Java live thread context for the imported campaign
- report indexed/failed row counts through the public response

It should depend on `persistence.elastic` repository ports and the
`conversation` thread context port.

Candidate public interfaces:

```java
public interface ImportUseCase {
    ImportCsvResponse importCsv(CsvImportCommand command);
}
```

### `agentbridge`

Boundary between Java Backend and the external Python Agent Core container.

This package is not the agent core. It is the Java-side bridge to Python Agent
Core.

Responsibilities:

- convert Java conversation commands into `InternalAgentTurn`
- submit turns to `POST /internal/agent/turns`
- subscribe to `WS /internal/agent/threads/{threadId}/stream`
- expose Python stream messages back to `conversation`
- own Java-to-Python `trace_context` and future `traceparent` propagation
- isolate Python timeout, parse, connection, and submit failures

Candidate public interfaces:

```java
public interface AgentTurnPort {
    void submitTurn(AgentTurnCommand command);
}

public interface AgentStreamPort {
    void subscribe(String threadId, AgentStreamListener listener);
}

public interface AgentStreamListener {
    void onMessage(String threadId, StreamMessage message);
}
```

### `approval`

Deterministic approval use case.

Responsibilities:

- validate that an approval gate exists
- validate approval target identity
- resolve user-edited final experiments or fall back to drafted experiments
- assemble approved `GrowthBriefDoc` and `CalendarEventDoc` documents
- persist approved documents through `persistence.elastic`
- return a frontend-safe approval result

It must not call Python Agent Core.

Candidate public interfaces:

```java
public interface ApprovalUseCase {
    ApprovalCommitResult approve(ApproveCommand command);
}
```

### `persistence.elastic`

Elastic adapter layer.

Responsibilities:

- bootstrap required Elastic indices
- upsert campaign working context
- bulk index imported `content_posts`
- check approval idempotency
- persist approved `growth_briefs` and `calendar_events`

Candidate ports:

```java
public interface CampaignRepository {
    void upsertCampaign(CampaignDoc campaign);
}

public interface ContentPostRepository {
    IndexResult bulkIndex(List<ContentPostDoc> posts);
}

public interface ApprovalDocumentRepository {
    boolean growthBriefExistsForThread(String threadId);
    void persistApproval(GrowthBriefDoc brief, List<CalendarEventDoc> events);
}
```

### `contracts`

Java records that mirror external contracts.

Target subpackages:

```text
contracts.publicapi      # Frontend <-> Java DTOs
contracts.agentbridge    # Java <-> Python DTOs
contracts.elastic     # Java -> Elastic documents
contracts.shared         # Signal, hypothesis, experiment payloads
```

The package should reflect container boundaries, not incidental Java layer
names.

### `observability`

Java service-level observability boundary.

Responsibilities:

- define correlation context and observed operations
- provide operation scopes for logs, metrics, traces, and MDC
- generate downstream trace context for `agentbridge`
- keep OpenTelemetry, Micrometer, MDC, and Google Cloud Operations details out of
  business components

Observability should be wired at component boundaries after the refactor, not
inside low-level business logic.

## Refactor Slices

The refactor should proceed in slices that leave the public contracts unchanged.

1. Extract `agentbridge`.
2. Split `persistence.elastic`.
3. Extract `importing`.
4. Extract `approval`.
5. Rebuild `conversation` around `ConversationCommandUseCase`.
6. Thin `api` and `websocket`.
7. Move DTOs into `contracts` once component ownership is stable.
8. Wire `observability` at the new component boundaries.

## Invariants

- Frontend still talks only to Java.
- Python Agent Core remains the only owner of agent reasoning.
- Java sends free-form turns to Python; Java handles deterministic UI actions.
- Java writes Elastic only for CSV import and human approval.
- Python stream blocks remain user-safe and are relayed as `StreamMessage.blocks[]`.
- Approval persistence remains Java-owned.
- Observability must not change product behavior.
