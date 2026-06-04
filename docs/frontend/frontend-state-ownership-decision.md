# LaunchPilot Frontend State Ownership Decision

Status: Draft v0.1  
Scope: Frontend state ownership, ViewModel boundaries, and future state-management replaceability  
Last updated: 2026-06-04

## Purpose

LaunchPilot is not a simple form or CRUD screen. The Experiment Planner is a stateful workroom over a long-running backend workflow:

```text
CSV input
-> import/index metrics
-> start agent run
-> observe WebSocket stream
-> review signal
-> review/edit experiment plan
-> approve
-> create immutable calendar/brief outputs
```

The frontend must therefore avoid leaking a specific state implementation, such as a reducer union, XState state, Zustand store shape, or query cache shape, into presentational UI.

This document defines which state belongs where and what interface boundary components should consume.

## Decision

Frontend state will be owned by boundary, lifetime, and sharing scope, not by one global store.

LaunchPilot will use feature-level ViewModels as the primary interface between state implementation and React components.

```text
State implementation
  - reducer
  - future statechart
  - future store slices
  - server-state cache
        ↓ hidden
Feature Controller / Presenter
        ↓ public interface
Feature ViewModel
        ↓
Presentational Components
```

Presentational components must depend on ViewModel fields and commands, not on the internal workflow state shape.

## Ownership Model

| State class | Examples | Owner | Public exposure |
| --- | --- | --- | --- |
| App shell state | current workspace, campaign identity, authenticated user, feature flags | App shell context or route loader | Shell ViewModel/context |
| Feature workflow state | selected CSV, import/run lifecycle, signal review, approval lifecycle, local draft experiment edits | `ExperimentPlanner` ViewModel implementation | Derived feature ViewModel only |
| Server state | campaign list, approved briefs, calendar events, run snapshots | API/query layer | Resource-specific query/projected data |
| Stream state | WebSocket connection, resume/replay, last received sequence, stream failure | Stream adapter plus feature workflow projection | Derived stream/progress ViewModel |
| Form/draft state | composer text, experiment title edits before approval | Feature ViewModel when it affects workflow; component local when isolated | Composer/review ViewModel |
| Local UI state | sidebar collapsed, inspector open, selected document, hover/menu/focus state | Closest component unless multiple sibling components coordinate on it | Local props or UI ViewModel |

## Non-Goals

- Do not centralize all frontend state in one global store.
- Do not persist pre-approval candidate experiment drafts outside frontend memory.
- Do not expose Python, Elastic, Gemini, or Phoenix state directly to the frontend.
- Do not make TanStack Query, XState, Zustand, Redux, or `useReducer` part of the component contract.
- Do not make small interaction state, such as hover or menu open state, part of the workflow machine.

## ViewModel Contract

The Experiment Planner UI should consume a stable interface shaped around what the screen needs to render and what actions the user can take.

The long-term public contract should move toward this shape:

```ts
export interface ExperimentPlannerViewModel {
  shell: PlannerShellView;
  screen: PlannerScreenView;
  composer: PlannerComposerView;
  progress: PlannerProgressView;
  thread: PlannerThreadView;
  inspector: PlannerInspectorView;
  approval: PlannerApprovalView;
  commands: PlannerCommands;
}
```

### Shell View

```ts
interface PlannerShellView {
  campaignName: string;
  campaignStatus: "active" | "needs_review" | "approved" | "error";
}
```

### Screen View

```ts
type PlannerScreenMode =
  | "empty"
  | "input_ready"
  | "importing"
  | "starting_run"
  | "connecting_stream"
  | "live_run"
  | "signal_review"
  | "plan_review"
  | "approved_summary"
  | "error";

interface PlannerScreenView {
  mode: PlannerScreenMode;
  intro: { title: string; description: string } | null;
  statusRows: Array<{ title: string; detail: string }>;
}
```

### Composer View

```ts
interface PlannerComposerView {
  value: string;
  fileName: string | null;
  canAttachCsv: boolean;
  canAnalyze: boolean;
  analyzeLabel: string;
  analyzeTitle?: string;
}
```

### Progress View

```ts
interface PlannerProgressView {
  visible: boolean;
  runLabel: string | null;
  title: string | null;
  detail: string | null;
  steps: ChecklistStep[];
}
```

### Inspector View

```ts
interface PlannerInspectorView {
  canToggle: boolean;
  activeGateKey: string | null;
  currentGate: GateReview | null;
  history: GateReview[];
}
```

### Thread View

```ts
interface PlannerThreadView {
  hasActivity: boolean;
  userMessages: AgentMessage[];
  assistantMessages: AgentMessage[];
  documents: AgentDocument[];
  observations: AgentObservation[];
  primaryExperiment: ExperimentItem | null;
}
```

### Approval View

```ts
interface PlannerApprovalView {
  canApprove: boolean;
  isApproving: boolean;
  draftExperiments: ExperimentItem[];
  finalExperiments: ExperimentItem[];
  primaryExperiment: ExperimentItem | null;
  receipt: ApproveExperimentPlanResponse | null;
  calendarEvents: CalendarEventRef[];
}
```

### Commands

```ts
interface PlannerCommands {
  selectCsv(file: File): void;
  updateQuestion(value: string): void;
  analyze(): Promise<void>;
  continueSignalReview(): void;
  editExperiment(experimentId: string, title: string): void;
  approve(): Promise<void>;
  reject(reason?: string): void;
  cancel(reason?: string): Promise<void>;
  reset(): void;
}
```

## Component Rules

React components should not read raw workflow implementation state.

Avoid:

```ts
view.state.tag === "importing_csv";
"agentRunId" in view.state;
view.agentState === "selected";
```

Prefer:

```ts
view.screen.statusRows;
view.composer.canAnalyze;
view.progress.visible;
view.inspector.canToggle;
view.approval.canApprove;
```

Components may keep truly local UI state when it does not affect workflow ownership.

Allowed local state examples:

- `sidebarCollapsed`
- hover/menu open state
- focused item
- purely visual disclosure state

Move state into the ViewModel when:

- more than one sibling component coordinates through it
- it changes available commands
- it affects workflow transitions
- it must survive component extraction
- it participates in error recovery, reconnect, approval, or reset behavior

## Implementation Boundary

The current implementation uses:

```text
useReducer(experimentPlannerReducer)
+ useExperimentPlannerController
+ API adapters
+ WebSocket adapter
+ local component state
```

This is acceptable for the MVP, but the public ViewModel must not expose `ExperimentPlannerState` directly.

Current known leakage to remove:

| Leakage | Why it is a problem | Target |
| --- | --- | --- |
| `ExperimentPlannerViewModel.state` | Exposes reducer union shape to components | Remove or make debug-only |
| UI checks `view.state.tag` | Couples UI to reducer implementation | Replace with `screen.mode`, `statusRows`, `progress.visible` |
| UI checks `"agentRunId" in state` | Couples UI to raw state variants | Replace with `progress.runLabel` |
| Page computes `canAnalyze` / `canApprove` | View rules spread into component | Move to `composer.canAnalyze` and `approval.canApprove` |
| Page computes `campaignStatus` | Shell projection spread into component | Move to `shell.campaignStatus` |
| Page computes `canToggleInspector` | Inspector ownership spread into component | Move to `inspector.canToggle` |
| Request builders accept raw state | API request shape tied to reducer union | Accept explicit request inputs |

## State Management Library Position

No additional state library is required by this decision.

The ownership boundary should be established before adopting a new implementation.

Potential future split:

| Need | Candidate |
| --- | --- |
| resource caching, refetch, server snapshots | TanStack Query or SWR |
| explicit workflow transitions, guards, nested/parallel state | XState/statecharts |
| shared app-level state with simple setters | Context or Zustand |
| enterprise backend lifecycle, audit, retry, compensation | Java/Python workflow or saga layer |

The component-facing ViewModel should remain stable if any of these implementations are introduced later.

## Migration Plan

1. Introduce feature ViewModel interface types.
2. Move derived display fields from `ExperimentPlannerPage.tsx` into the controller/presenter layer.
3. Stop exposing raw `ExperimentPlannerState` from `ExperimentPlannerViewModel`.
4. Replace component `state.tag` and `agentState` checks with ViewModel fields.
5. Change request builders to accept explicit request input objects instead of raw workflow state.
6. Add projection tests for ViewModel fields.
7. Re-evaluate whether the internal implementation should remain `useReducer` or move to a statechart.

## Acceptance Criteria

- Presentational components do not import `ExperimentPlannerState` or `ExperimentPlannerEvent`.
- Presentational components do not inspect `state.tag`.
- Components render from ViewModel sections such as `screen`, `composer`, `progress`, `thread`, `inspector`, and `approval`.
- All user commands flow through `PlannerCommands`.
- API adapters and WebSocket adapters remain behind interfaces.
- A future replacement of the workflow implementation does not require broad presentational component rewrites.
