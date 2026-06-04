# LaunchPilot MVP Requirements Traceability

Status: Draft v0.1  
Scope: MVP user scenario, frontend state machine, contracts, and acceptance coverage  
Last updated: 2026-06-01

## Purpose

This document keeps the MVP implementation grounded in the agreed user scenario and architecture.

It is the review surface before screen design and code construction. When a requirement changes, update this table first, then update the state machine, contracts, and tests.

## Product Frame

Primary user: content or growth manager.

Primary job: upload campaign performance data, ask what to test next, review evidence-backed experiment candidates, adjust the final plan, and approve it into a durable brief/calendar artifact.

MVP priority: one complete happy path that runs end to end. Failure and retry scenarios are intentionally deferred until after the first working MVP.

Design reference: [`awesome-design-md/design-md/apple/DESIGN.md`](https://github.com/VoltAgent/awesome-design-md/blob/main/design-md/apple/DESIGN.md). Use its Apple-inspired restraint: near-invisible UI chrome, confident typography, white/off-white/near-black canvases, one quiet blue action color, and crisp hierarchy. For LaunchPilot this should be translated into a data workroom, not a marketing landing page.

## Requirement Traceability Matrix

| ID | Requirement | Source | State/Event | UI Surface | Contract/API | Test Coverage | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MVP-R1 | User can provide SNS metric CSV data for a campaign. | C4 C1/C2, scenario `import_csv` | `idle`, `csv_selected`, `IMPORT_REQUESTED`, `importing_csv` | CSV input, selected file review | `POST /api/import/csv` | Scenario contract validates import fixture | Covered for contract, pending UI |
| MVP-R2 | MVP UI uses one primary `Analyze` action after CSV selection; the app may internally import first, then start analysis. | Playwright happy path, frontend state-machine review | `IMPORT_REQUESTED` followed by `RUN_AGENT_REQUESTED` after successful import | Single primary Analyze button, progress copy distinguishes importing from analysis | `POST /api/import/csv`, then `POST /api/agent/run` | Playwright expects one user click | Resolved P1 |
| MVP-R3 | Frontend only calls Java public APIs. | Frontend state machine principle, C4 C2 | All API side effects | No direct Python, Elastic, Gemini, or Phoenix UI calls | `contracts/01-frontend-java` | Contract map and scenario actors | Covered |
| MVP-R4 | Java starts the Python ADK agent asynchronously and returns quickly. | C4 C2/C3, scenario `run_agent`, `internal_start_agent` | `starting_analysis`, `RUN_AGENT_ACCEPTED`, `analysis_pending` | Non-blocking starting state | `POST /api/agent/run`, `POST /internal/agent/runs` | Scenario validates public/internal run ID stability | Covered |
| MVP-R5 | Frontend subscribes to the WebSocket stream for live agent progress; reconnect replays missed events via `connection.resume`/`full_sync`. REST `GET` is a coarse snapshot fallback, not a polling loop. | `01/asyncapi.yaml`, FE state machine | `analysis_pending`, `stream_connecting`, `analysis_running`, `STREAM_EVENT_RECEIVED`, `SNAPSHOT_RECOVERED` | Live timeline, tool/evidence activity | `WS /api/agent/runs/{agent_run_id}/stream` plus `GET` fallback | FE reducer implemented; WS e2e pending | Needs WS test |
| MVP-R6 | Successful candidate generation stops at `WAITING_FOR_APPROVAL`; approval is human-owned. | Java-Python contract, scenario `poll_ready` | `waiting_for_approval` | Review workroom | Agent run response payload | Contract verifier checks terminal status mapping | Covered |
| MVP-R7 | Candidate experiments are not persisted as final business artifacts before approval. | C4 sequence note, Elastic contract, state machine principle | `waiting_for_approval`, `editing_plan` | Local editable draft | No Elastic write until approval | Scenario persistence starts only after `approve_plan` | Covered |
| MVP-R8 | User can review evidence-backed signals, hypotheses, and experiment plans. | Main user scenario, Agent output contract | `waiting_for_approval` | Three-panel workroom: signals, hypotheses, experiments | `AgentResultPayload` | Playwright checks signal, hypothesis, experiment title | Covered for happy path |
| MVP-R9 | User can adjust final experiment text before approval. | C4 Phase 2, Elastic contract preserves user edits | `EDIT_EXPERIMENT`, `editing_plan` | Editable experiment fields, title at minimum for MVP | `ApproveExperimentPlanRequest.final_experiments` | Playwright edits title and expects final text | Covered for title edit |
| MVP-R10 | Experiment selection is not a first-class checkbox flow for MVP; selection can be expressed by chat or future command UI. | User decision on 2026-06-01 | No required `TOGGLE_EXPERIMENT` UI for MVP | Chat/action instruction area, approve all visible experiments by default | Approval request defaults to all draft experiments | Not tested now | Deferred by decision |
| MVP-R11 | Approval creates immutable growth brief and calendar event artifacts. | C4 Phase 2, Elastic contract, scenario persistence | `APPROVE_REQUESTED`, `approving`, `APPROVE_SUCCEEDED`, `approved` | Approval progress, calendar/brief confirmation | `POST /api/agent/actions/{agent_run_id}/approve`, `growth_briefs`, `calendar_events` | Scenario validates links; Playwright checks confirmation | Covered |
| MVP-R12 | Approved artifacts preserve linear campaign continuity. | C4 Phase 3, user clarification | `approved`, `restore_selecting`, `restoring_context`, next `starting_analysis` with lineage | Prior brief picker, continuation context banner, previous hypothesis/action/result lane | `parent_brief_id` in agent run request, `load_growth_brief_context` | Contract support exists; UI/state coverage added, E2E later | Needs implementation |
| MVP-R13 | A new session can continue from a prior approved brief and its action outcome. | C4 Phase 3, Elastic MCP contract | `RESTORE_CONTEXT_REQUESTED`, `RESTORE_CONTEXT_SUCCEEDED`, `RUN_AGENT_REQUESTED` | Continue previous analysis action | `parent_brief_id`, `growth_briefs`, `load_growth_brief_context` | Scenario contract has parent context fixtures, no Playwright yet | Needs implementation |
| MVP-R14 | Agent evidence retrieval must be grounded by MCP EvidenceRef outputs. | Agent-Elastic MCP contract, scenario invariants | Agent-side, reflected in payload | Evidence refs visible or inspectable | `contracts/04-agent-elastic-mcp`, `AgentResultPayload` | Scenario validates evidence grounding | Covered for contract |
| MVP-R15 | OpenInference traces link agent diagnostics to observability. | Observability contract, scenario `emit_openinference_trace` | Agent-side diagnostics | Optional trace/debug affordance later | `contracts/06-observability` | Scenario validates trace links | Covered for contract |
| MVP-R16 | MVP visual language should feel like a precise premium workroom, not a landing page. | Apple `DESIGN.md` reference | All screens | Dense but calm layout, white/off-white/near-black surfaces, one blue action color, generous whitespace, clear hierarchy, minimal ornament | N/A | Visual review after UI implementation | Pending UI |

## MVP Interaction Decisions

- The primary user action after selecting a CSV is `Analyze`.
- `Analyze` may perform two internal effects in order: import CSV, then start agent analysis.
- The UI should show distinct progress states so the user can tell whether data is being imported or the agent is reasoning.
- Experiment checkbox selection is not required for MVP. Default approval includes all current draft experiments unless a later chat/command flow changes the draft set.
- Failure and retry scenarios remain documented in the state machine but are not MVP acceptance blockers before the first working happy path.

## Linearity Requirement

The product must preserve a campaign's decision chain:

1. Previous approved hypothesis.
2. Approved action or experiment.
3. Observed result or metric outcome.
4. Next hypothesis and next action.

When continuing from a prior brief, the UI must carry `parent_brief_id` into the next agent run and make the inherited context visible enough that the user understands why the new recommendation follows from the previous one.

The next generated plan should not feel like a fresh unrelated analysis. It should be framed as the next step in the same campaign learning loop.

## Review Rules

- If a new state is added, it must map to at least one requirement above.
- If a new API call is added, it must identify the owning contract folder.
- If a new MVP screen is added, it must identify which user decision it supports.
- If a Playwright assertion changes, update the matching requirement row.
