# LaunchPilot Frontend State Machine

Status: Draft v0.2  
Scope: Experiment Planner frontend state machine for the main analysis-to-approval flow  
Last updated: 2026-06-02

## Purpose

The frontend is a stateful workroom over an asynchronous backend contract.

This state machine translates the contracts and executable scenario into implementation rules for the Next.js UI. It is the bridge between:

- `contracts/01-frontend-java/frontend-types.ts`
- `scenarios/main-analysis-approval.scenario.json`
- `e2e/main-analysis-approval.mock.spec.ts`
- `docs/product/mvp-product-requirements.md`

## Design Principles

- The frontend only talks to the Java Backend public API.
- Candidate experiment plans live in frontend memory until approval.
- The WebSocket run stream is the primary source of truth for live analysis progress.
- Backend snapshots are the fallback source of truth for reconnect, refresh recovery, and stream failure.
- User edits are local draft state until `APPROVE_SENT`.
- Approval success creates calendar/brief output and moves the UI into an approved state.
- A continued session must preserve the linear chain from prior hypothesis to approved action, observed result, and next recommendation.
- The reducer should make impossible states unrepresentable.

## High-Level State Diagram

```mermaid
stateDiagram-v2
  [*] --> idle

  idle --> csv_selected: SELECT_CSV
  csv_selected --> importing_csv: IMPORT_REQUESTED
  importing_csv --> import_succeeded: IMPORT_SUCCEEDED
  importing_csv --> import_failed: IMPORT_FAILED
  import_failed --> csv_selected: SELECT_CSV

  import_succeeded --> starting_analysis: RUN_AGENT_REQUESTED
  starting_analysis --> analysis_pending: RUN_AGENT_ACCEPTED
  starting_analysis --> analysis_failed: RUN_AGENT_FAILED

  analysis_pending --> stream_connecting: STREAM_CONNECT_REQUESTED
  stream_connecting --> analysis_running: STREAM_CONNECTED
  stream_connecting --> analysis_running: SNAPSHOT_RECOVERED
  stream_connecting --> analysis_failed: STREAM_FAILED
  analysis_running --> analysis_running: STREAM_EVENT_RECEIVED
  analysis_running --> waiting_for_approval: APPROVAL_REQUESTED
  analysis_running --> analysis_cancelled: RUN_CANCELLED
  analysis_running --> analysis_failed: RUN_FAILED

  waiting_for_approval --> editing_plan: EDIT_EXPERIMENT
  editing_plan --> editing_plan: EDIT_EXPERIMENT
  waiting_for_approval --> approving: APPROVE_SENT
  editing_plan --> approving: APPROVE_SENT
  waiting_for_approval --> analysis_cancelled: CANCEL_SENT
  editing_plan --> analysis_cancelled: CANCEL_SENT

  approving --> approved: RUN_COMPLETED
  approving --> approval_failed: APPROVE_FAILED
  approval_failed --> editing_plan: EDIT_EXPERIMENT
  approval_failed --> approving: APPROVE_SENT

  analysis_failed --> idle: RESET
  analysis_cancelled --> idle: RESET
  approved --> idle: RESET

  approved --> restore_selecting: CONTINUE_FROM_BRIEF
  restore_selecting --> restoring_context: RESTORE_CONTEXT_REQUESTED
  restoring_context --> restored_context: RESTORE_CONTEXT_SUCCEEDED
  restored_context --> starting_analysis: RUN_AGENT_REQUESTED
  restoring_context --> analysis_failed: RESTORE_CONTEXT_FAILED
```

## State Model

Recommended TypeScript shape:

```ts
import type {
  AgentObservation,
  AgentResultPayload,
  AgentRunStatus,
  AgentRunStatusResponse,
  AgentStepSnapshot,
  AgentStreamServerEvent,
  ApprovalGateRequest,
  ApproveExperimentPlanResponse,
  CalendarEventRef,
  ExperimentItem,
  ImportCsvResponse,
  ToolCallLog,
} from "@/contracts/frontend-types";

type ExperimentPlannerState =
  | { tag: "idle" }
  | { tag: "csv_selected"; file: File }
  | { tag: "importing_csv"; file: File }
  | { tag: "import_succeeded"; file: File; importResult: ImportCsvResponse }
  | { tag: "import_failed"; file?: File; message: string }
  | {
      tag: "starting_analysis";
      source:
        | { kind: "csv_import"; importResult: ImportCsvResponse }
        | {
            kind: "continued_brief";
            parentBriefId: string;
            previousHypothesis: string;
            previousActionSummary: string;
            observedResultSummary: string | null;
            continuityPrompt: string;
          };
    }
  | {
      tag: "analysis_pending";
      agentRunId: string;
      streamUrl: string;
      snapshotUrl: string;
      status: "PENDING";
      toolLogs: ToolCallLog[];
    }
  | {
      tag: "stream_connecting";
      agentRunId: string;
      streamUrl: string;
      snapshotUrl: string;
      toolLogs: ToolCallLog[];
    }
  | {
      tag: "analysis_running";
      agentRunId: string;
      streamUrl: string;
      snapshotUrl: string;
      status: Exclude<AgentRunStatus, "PENDING" | "WAITING_FOR_APPROVAL" | "SUCCESS" | "FAILED" | "CANCELLED">;
      currentStage: string | null;
      steps: AgentStepSnapshot[];
      observations: AgentObservation[];
      toolLogs: ToolCallLog[];
    }
  | {
      tag: "waiting_for_approval";
      agentRunId: string;
      approvalId: string;
      payload: AgentResultPayload;
      selectedExperimentIds: string[];
      draftExperiments: ExperimentItem[];
      steps: AgentStepSnapshot[];
      observations: AgentObservation[];
      toolLogs: ToolCallLog[];
    }
  | {
      tag: "editing_plan";
      agentRunId: string;
      approvalId: string;
      payload: AgentResultPayload;
      selectedExperimentIds: string[];
      draftExperiments: ExperimentItem[];
      steps: AgentStepSnapshot[];
      observations: AgentObservation[];
      toolLogs: ToolCallLog[];
      dirty: true;
    }
  | {
      tag: "approving";
      agentRunId: string;
      approvalId: string;
      payload: AgentResultPayload;
      selectedExperimentIds: string[];
      draftExperiments: ExperimentItem[];
    }
  | {
      tag: "approved";
      agentRunId: string;
      approval: ApproveExperimentPlanResponse;
      calendarEvents: CalendarEventRef[];
      finalExperiments: ExperimentItem[];
    }
  | {
      tag: "restore_selecting";
      parentBriefId: string;
    }
  | {
      tag: "restoring_context";
      parentBriefId: string;
    }
  | {
      tag: "restored_context";
      parentBriefId: string;
      previousHypothesis: string;
      previousActionSummary: string;
      observedResultSummary: string | null;
      continuityPrompt: string;
    }
  | {
      tag: "analysis_cancelled";
      agentRunId: string;
      message: string;
    }
  | {
      tag: "analysis_failed" | "approval_failed";
      agentRunId?: string;
      message: string;
      recoverable: boolean;
    };
```

## Events

```ts
type ExperimentPlannerEvent =
  | { type: "SELECT_CSV"; file: File }
  | { type: "IMPORT_REQUESTED" }
  | { type: "IMPORT_SUCCEEDED"; importResult: ImportCsvResponse }
  | { type: "IMPORT_FAILED"; message: string }
  | { type: "RUN_AGENT_REQUESTED" }
  | { type: "RUN_AGENT_ACCEPTED"; agentRunId: string; streamUrl: string; snapshotUrl: string }
  | { type: "RUN_AGENT_FAILED"; message: string }
  | { type: "STREAM_CONNECT_REQUESTED" }
  | { type: "STREAM_CONNECTED" }
  | { type: "STREAM_EVENT_RECEIVED"; event: AgentStreamServerEvent }
  | { type: "SNAPSHOT_RECOVERED"; snapshot: AgentRunStatusResponse }
  | { type: "STREAM_FAILED"; agentRunId?: string; message: string }
  | { type: "APPROVAL_REQUESTED"; approval: ApprovalGateRequest; toolLogs: ToolCallLog[] }
  | { type: "TOGGLE_EXPERIMENT"; experimentId: string; selected: boolean }
  | { type: "EDIT_EXPERIMENT"; experimentId: string; patch: Partial<ExperimentItem> }
  | { type: "APPROVE_SENT" }
  | { type: "RUN_COMPLETED"; approval: ApproveExperimentPlanResponse }
  | { type: "APPROVE_FAILED"; message: string }
  | { type: "CANCEL_SENT"; reason?: string }
  | { type: "RUN_CANCELLED"; message: string }
  | { type: "CONTINUE_FROM_BRIEF"; parentBriefId: string }
  | { type: "RESTORE_CONTEXT_REQUESTED" }
  | {
      type: "RESTORE_CONTEXT_SUCCEEDED";
      previousHypothesis: string;
      previousActionSummary: string;
      observedResultSummary: string | null;
      continuityPrompt: string;
    }
  | { type: "RESTORE_CONTEXT_FAILED"; message: string }
  | { type: "RESET" };
```

## Transition Rules

| From | Event | To | Notes |
| --- | --- | --- | --- |
| `idle` | `SELECT_CSV` | `csv_selected` | Store the selected file only. |
| `csv_selected` | `IMPORT_REQUESTED` | `importing_csv` | Calls `POST /api/import/csv`. |
| `importing_csv` | `IMPORT_SUCCEEDED` | `import_succeeded` | Store `ImportCsvResponse`. |
| `importing_csv` | `IMPORT_FAILED` | `import_failed` | Show retry affordance. |
| `import_succeeded` | `RUN_AGENT_REQUESTED` | `starting_analysis` | Calls `POST /api/agent/run` with `source.kind = "csv_import"`. |
| `starting_analysis` | `RUN_AGENT_ACCEPTED` | `analysis_pending` | Store `agent_run_id`, `stream_url`, and `next_poll_url`. |
| `analysis_pending` | `STREAM_CONNECT_REQUESTED` | `stream_connecting` | Open `WS /api/agent/runs/{agent_run_id}/stream`. |
| `stream_connecting` | `STREAM_CONNECTED` | `analysis_running` | Initialize empty step, observation, and tool timelines. |
| `stream_connecting` | `SNAPSHOT_RECOVERED` | `analysis_running` or `waiting_for_approval` | Use REST snapshot when stream reconnect needs recovery. |
| `analysis_running` | `STREAM_EVENT_RECEIVED` | `analysis_running` | Merge step updates, append observations, append/replace tool logs. |
| `analysis_running` | `APPROVAL_REQUESTED` | `waiting_for_approval` | Initialize `draftExperiments` from `approval.payload.experiment_plan.items`. |
| `waiting_for_approval` | `EDIT_EXPERIMENT` | `editing_plan` | Local-only draft mutation. |
| `waiting_for_approval` / `editing_plan` | `APPROVE_SENT` | `approving` | Sends `approval.approve` over WebSocket, or REST fallback if stream is unavailable. |
| `approving` | `RUN_COMPLETED` | `approved` | State passing to calendar can use local final experiments. |
| `approving` | `APPROVE_FAILED` | `approval_failed` | Preserve local draft through retry. |
| `analysis_running` / `waiting_for_approval` / `editing_plan` | `CANCEL_SENT` | `analysis_cancelled` | Sends `run.cancel` over WebSocket, or REST fallback if stream is unavailable. |
| `approved` | `CONTINUE_FROM_BRIEF` | `restore_selecting` | Start a new analysis from an approved `growth_brief_id`. |
| `restore_selecting` | `RESTORE_CONTEXT_REQUESTED` | `restoring_context` | Load previous hypothesis, approved action, and observed result context. |
| `restoring_context` | `RESTORE_CONTEXT_SUCCEEDED` | `restored_context` | Show continuity context before the next run. |
| `restored_context` | `RUN_AGENT_REQUESTED` | `starting_analysis` | Calls `POST /api/agent/run` with `source.kind = "continued_brief"` and `parent_brief_id`. |
| `restoring_context` | `RESTORE_CONTEXT_FAILED` | `analysis_failed` | Restore failure blocks continuation. |
| `analysis_failed` / `approved` | `RESET` | `idle` | Start over. |

## Screen Mapping

| State | Primary Screen | Required UI |
| --- | --- | --- |
| `idle` | Empty Experiment Planner | CSV input labeled with `CSV`; disabled or secondary analyze button. |
| `csv_selected` | Input Ready | File chip, optional instructions, enabled `Analyze` action. No run progress yet. |
| `importing_csv` | Import Progress | Main-stream system status for uploading/indexing. Disable repeat Analyze and CSV replacement; keep instructions editable. No assistant bubble, inspector, or review gate. |
| `import_succeeded` | Transient Import Complete | Store `ImportCsvResponse`; immediately dispatch `RUN_AGENT_REQUESTED` without a second user click. Show only a short system status. |
| `starting_analysis` | Starting Agent Run | Progress step `Start agent run` active. Keep composer text editable; do not open inspector. |
| `analysis_pending` | Run Accepted | Store run ID and stream URL. Progress step moves toward `Connect stream`; no agent result is shown yet. |
| `stream_connecting` | Connecting Stream | Progress step `Connect stream` active with snapshot recovery fallback. No assistant result until stream events arrive. |
| `analysis_running` | Agent Workspace | Fixed agent run status, streamed observations in the thread, cancel action, inspector artifacts. |
| `waiting_for_approval` | Review Surface | Signals, hypotheses, experiment plan, editable experiment fields, approve/reject/cancel controls. |
| `editing_plan` | Review Surface | Dirty indicator, selected experiment count, approve/reject/cancel controls. |
| `approving` | Approval In Progress | Disable edits and show persistence status. |
| `approved` | Calendar / Brief Confirmation | Approved experiment title and approval/calendar confirmation. |
| `analysis_cancelled` | Cancelled Run | Cancellation confirmation and restart action. |
| `analysis_failed` | Recoverable Error | Failure message and reset/retry actions. |
| `approval_failed` | Approval Error | Preserve draft and allow retry. |
| `restore_selecting` | Continue Prior Brief | Selected prior brief ID and continue action. |
| `restoring_context` | Restoring Context | Loading prior brief lineage. |
| `restored_context` | Continuity Workroom | Previous hypothesis, approved action, observed result, next analysis prompt. |

## API Side Effects

| Event | API | Contract |
| --- | --- | --- |
| `IMPORT_REQUESTED` | `POST /api/import/csv` | `contracts/01-frontend-java/examples/import-csv-response.json` |
| `RUN_AGENT_REQUESTED` | `POST /api/agent/run` | `contracts/01-frontend-java/examples/agent-run-accepted-response.json` |
| `STREAM_CONNECT_REQUESTED` | `WS /api/agent/runs/{agent_run_id}/stream` | `agent-stream-*-event.json` examples |
| `SNAPSHOT_RECOVERED` | `GET /api/agent/runs/{agent_run_id}` | running or ready agent run response |
| `APPROVE_SENT` | `approval.approve` WebSocket command, with REST approve fallback | `agent-stream-approval-approve-command.json`, `approve-experiment-plan-response.json` |
| `CANCEL_SENT` | `run.cancel` WebSocket command, with REST cancel fallback | `agent-stream-cancel-command.json` |
| `RESTORE_CONTEXT_REQUESTED` | Frontend prepares local lineage context from the approved brief or selected history entry | `contracts/03-java-elastic/examples/growth-brief.json` |
| continued `RUN_AGENT_REQUESTED` | `POST /api/agent/run` with `parent_brief_id` | `contracts/01-frontend-java/openapi.yaml`, `contracts/04-agent-elastic-mcp/examples/load-growth-brief-context-response.json` |

## MVP Analyze Action

For the MVP, the visible primary action after CSV selection is a single `Analyze` button.

Internally, this button runs two ordered effects:

1. Dispatch `IMPORT_REQUESTED` and call `POST /api/import/csv`.
2. After `IMPORT_SUCCEEDED`, dispatch `RUN_AGENT_REQUESTED` and call `POST /api/agent/run`.

The state machine keeps `import_succeeded` as an explicit state because importing and analysis are different backend responsibilities. The UI may pass through it immediately without requiring a second user click.

Normal import success is not a review gate. The import result can appear as a small system status or history line, but it must not open the action panel or require a `Continue analysis` button.

The user-facing progress copy must still distinguish import work from agent reasoning.

## Approval Request Construction

When moving from `waiting_for_approval` or `editing_plan` into `approving`, construct a WebSocket `approval.approve` command. If the stream is unavailable, construct the REST fallback:

```ts
const request: ApproveExperimentPlanRequest = {
  experiment_plan_id: state.payload.experiment_plan.id,
  approved_by: "demo_user",
  final_experiments: state.draftExperiments.filter((experiment) =>
    state.selectedExperimentIds.includes(experiment.id),
  ),
};
```

Validation before approval:

- At least one experiment must be selected.
- Every selected experiment must have `title`, `hook`, `cta`, `success_criteria`, `scheduled_at`, and `production_brief`.
- `experiment_plan_id` must come from the latest `approval.requested` payload, or the recovered snapshot payload.
- MVP default is to approve all draft experiments. Dedicated checkbox selection is deferred; a later chat or command interaction may mutate the draft experiment set before approval.

## Continuity And Restore Rules

Continuation is part of the campaign learning loop, not a generic history feature.

When the user continues from an approved brief, preserve this lineage:

1. `parent_brief_id`
2. previous approved hypothesis
3. previous approved action or experiment
4. observed result or metric outcome, when available
5. next analysis question

`RUN_AGENT_REQUESTED` from `restored_context` must include `parent_brief_id` in the request body. The Python agent then uses `load_growth_brief_context` through the Elastic MCP wrapper to retrieve the approved prior context.

The UI must make the lineage visible in the continuation surface. The next recommendation should be framed as a follow-up to the previous hypothesis/action/result chain, not as an unrelated fresh analysis.

## Stream And Snapshot Rules

- Open the stream immediately after `RUN_AGENT_ACCEPTED`.
- Keep active progress in the WebSocket event timeline, not repeated polling ticks.
- Request a REST snapshot after reconnect, hard refresh, or unexpected stream close.
- Stop the active stream lifecycle on `WAITING_FOR_APPROVAL`, `SUCCESS`, `FAILED`, or `CANCELLED`.
- Treat `SUCCESS` from public API as already approved/restored state, not as the normal Python terminal state.

## Playwright Acceptance Hooks

The current happy-path E2E spec expects these accessible affordances:

- File input label containing `CSV`.
- Primary analysis button named `Analyze`, `Analyse`, or `Run analysis`.
- Running text containing `Analyzing`, `Running evidence`, or `Searching evidence`.
- Generated signal text: `BTS shorts outperformed recent baseline`.
- Generated hypothesis text containing `raw behind-the-scenes clips may be converting`.
- Generated experiment title: `BTS face-first hook test`.
- Editable title textbox accessible by `Experiment title` or `Title`.
- Approval button named `Approve` or `Approve Experiments`.
- Approved/calendar confirmation text containing `Human approval processed`, `Approved`, or `Calendar`.

These hooks are not decorative; they are the first executable acceptance target for frontend implementation.

## Reducer Guidance

- Keep all network effects outside the reducer.
- Reducer handles events only.
- Effects observe state changes and dispatch follow-up events.
- Do not store pending candidate experiments in Elastic before approval.
- Keep original `payload` immutable and apply user edits to `draftExperiments`.
- `selectedExperimentIds` should default to all experiment IDs from the ready payload for the happy path.
- Keep continuity context immutable during a continued run; user edits apply to the next draft, not to the prior approved brief.
