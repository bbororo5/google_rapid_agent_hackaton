# LaunchPilot Frontend Architecture Decision

Status: Accepted v0.2  
Scope: Frontend MVP implementation architecture  
Last updated: 2026-06-02

## Decision

The LaunchPilot frontend will use a feature-based React/Next.js architecture:

```text
Feature-based React Architecture
+ State Machine Reducer
+ Controller Hook
+ HTTP API Adapter
+ Agent Stream Adapter
+ Contract Types
+ Presentational Components
```

We will not directly port Flutter-style MVVM into React. We will keep the useful MVVM principles, but express them with React and Next.js-native patterns.

## Why Not Literal MVVM

Flutter's official architecture guide recommends MVVM with views, view models, repositories, and services. That is a good fit for Flutter because the framework and ecosystem commonly model feature logic through view models and commands.

React and Next.js have a different center of gravity:

- React official guidance uses component state, reducer extraction, and context/custom hooks for scaling state logic.
- Next.js App Router is file-system route based and supports colocating implementation files with routes or using `src`.
- Modern React codebases commonly separate local UI state from server state.
- Feature-folder organization is widely recommended in Redux's official style guide because it keeps related logic together.

Therefore, LaunchPilot should preserve MVVM's separation of concerns without introducing React-unidiomatic view model classes.

## References

- Flutter app architecture guide: `https://docs.flutter.dev/app-architecture/guide`
- React managing state: `https://react.dev/learn/managing-state`
- React `useReducer`: `https://react.dev/reference/react/useReducer`
- Next.js App Router project structure: `https://nextjs.org/docs/app/getting-started/project-structure`
- Next.js data fetching: `https://nextjs.org/docs/app/getting-started/fetching-data`
- Redux style guide, feature folders: `https://redux.js.org/style-guide/`
- TanStack Query overview: `https://tanstack.com/query/v3/overview`

## Architecture Mapping

| Flutter MVVM Concept | LaunchPilot React/Next Concept | Responsibility |
| --- | --- | --- |
| View | React presentational components | Render UI and forward user events. |
| ViewModel | `useExperimentPlannerController` hook | Bind state, events, effects, and API calls for the Experiment Planner feature, then expose a stable ViewModel interface to components. |
| Repository | `experimentPlannerApi.ts` and `agentStreamApi.ts` interfaces | Own the frontend-facing HTTP and WebSocket operations for the feature. HTTP follows `openapi.yaml`; WebSocket messages follow `asyncapi.yaml`. |
| Service | `fetch`, `WebSocket`, or mock adapter | Perform concrete HTTP calls, stream connection, or fixture-backed mock responses. |
| UI State implementation | `experimentPlannerReducer.ts` and `ExperimentPlannerState` | Represent the finite state machine internally. Components should consume the ViewModel projection, not the raw state implementation. |
| Commands | Controller methods | Expose actions like `selectCsv`, `analyze`, `editExperiment`, `approve`, `continueFromBrief`. |
| Domain rules | Reducer transitions and request builders | Prevent impossible states and keep contract payloads valid. |

## Recommended App Layout

The frontend app should live under `apps/frontend`.

```text
apps/frontend/
  src/
    app/
      layout.tsx
      page.tsx
      globals.css

    features/
      campaign-planner/
        api/
          agentStreamApi.ts
          mockExperimentPlannerApi.ts
          mockAgentStreamApi.ts
          experimentPlannerApi.ts
        components/
          ApprovalPanel.tsx
          BriefingPanel.tsx
          SignalReviewPanel.tsx
          Topbar.tsx
          CampaignAgentWorkspace.tsx
        hooks/
          useExperimentPlannerController.ts
        state/
          experimentPlannerReducer.ts
          experimentPlannerTypes.ts
          experimentPlannerRequests.ts

    shared/
      styles/
        tokens.css
      ui/
      lib/
```

## Layer Responsibilities

### `src/app`

Next.js App Router entry point.

Keep route files thin. The home route should render campaign discovery, while campaign workflow routes render the Experiment Planner feature and avoid embedding feature logic directly in `page.tsx`.

### `features/campaign-planner/components`

Presentational components.

Allowed:

- layout logic
- rendering based on state
- calling controller callbacks
- accessibility labels and visual states

Avoid:

- direct API calls
- contract fixture imports
- polling loops
- request body construction
- reducer transition logic

### `features/campaign-planner/hooks/useExperimentPlannerController.ts`

The React equivalent of the feature ViewModel.

Responsibilities:

- owns `useReducer`
- exposes a stable feature ViewModel rather than raw `ExperimentPlannerState`
- exposes command callbacks for components
- runs effects such as import, start run, stream connection, snapshot recovery, cancel, and approve
- depends on `ExperimentPlannerApi` and `AgentStreamApi`
- keeps network effects outside the reducer

### `features/campaign-planner/state`

Pure state machine layer.

Responsibilities:

- define `ExperimentPlannerState`
- define `ExperimentPlannerEvent`
- implement `experimentPlannerReducer`
- construct approval and agent-run request payloads in pure helper functions
- encode continuation rules around `parent_brief_id`

This layer should be unit-testable without React.

### `features/campaign-planner/api`

Frontend API boundary.

`experimentPlannerApi.ts` defines the HTTP interface that the controller uses.

`agentStreamApi.ts` defines the WebSocket stream interface for active runs:

- connect to `stream_url` from `AgentRunAcceptedResponse`
- emit `AgentStreamServerEvent` values to the controller
- send `AgentStreamClientCommand` values for cancel, approval edit, approve, and reject
- close and reconnect without leaking component state
- treat `contracts/01-frontend-java/asyncapi.yaml` as the source contract for message names and payloads

`mockExperimentPlannerApi.ts` can read local contract examples while the Java backend is unavailable.

`mockAgentStreamApi.ts` can replay stream example events while the Java backend is unavailable.

Later, real implementations can call the Java public API and WebSocket stream without changing presentational components or reducer logic.

## Server State And Client State

Keep two kinds of state separate:

- client state: selected CSV file, reducer tag, local draft edits, selected prior brief, composer text
- server state: import result, agent run status, stream events, ready payload, approval response

For the MVP, the controller can manage both with `useReducer` and simple async effects because the flow is one screen and one happy path. Active run progress should prefer the WebSocket stream; `GET /api/agent/runs/{agent_run_id}` is the snapshot fallback.

After the MVP, introduce TanStack Query or SWR if server-state concerns grow:

- caching prior briefs
- refetching campaign history
- retrying failed stream connections
- invalidating calendar or brief queries after approval

Do not introduce a server-state library before the first happy-path implementation unless the code starts duplicating cache, retry, or synchronization logic.

## State Machine Choice

Use a hand-written reducer for MVP.

Rationale:

- the state machine is already documented
- React officially supports reducer-based state management
- the happy path is narrow enough to avoid introducing XState immediately
- a reducer keeps the first implementation small and testable

Revisit XState after MVP if:

- parallel states become important
- failure/retry branches grow
- continuation sessions create nested statecharts
- visual statechart tooling would help the team

## Implementation Rules

- Keep route files thin.
- Keep API calls out of components.
- Keep reducer pure.
- Keep fixture-backed mock API behind the same interface as the future real API.
- Do not store pending candidate experiments outside frontend memory before approval.
- Make Playwright happy path the first executable target.
- Treat screen architecture and state machine documents as implementation constraints, not suggestions.
- Treat `docs/frontend/frontend-state-ownership-decision.md` as the boundary rule for what state can be exposed to presentational components.

## First MVP Build Order

1. Create `apps/frontend` with Next.js, TypeScript, and styling setup.
2. Add `ExperimentPlannerState`, `ExperimentPlannerEvent`, and `experimentPlannerReducer`.
3. Add `ExperimentPlannerApi` and fixture-backed `mockExperimentPlannerApi`.
4. Add `AgentStreamApi` and fixture-backed `mockAgentStreamApi`.
5. Add `useExperimentPlannerController`.
6. Build `AppShell`, `SidebarShell`, `MainShell`, `Topbar`, `CampaignAgentWorkspace`, and its major panels.
7. Pass `e2e/main-analysis-approval.mock.spec.ts`.
