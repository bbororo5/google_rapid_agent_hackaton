# LaunchPilot Frontend Screen Architecture

Status: Draft v0.1  
Scope: MVP War Room layout for the frontend implementation  
Last updated: 2026-06-01

## Purpose

This document translates the MVP requirements and frontend state machine into a concrete screen structure.

The product should feel conversational like Gemini, but it is not a generic chat app. LaunchPilot is a data marketing workroom where evidence, hypotheses, experiment drafts, and approval actions must stay visible and actionable.

Related documents:

- `docs/product/mvp-requirements-traceability.md`
- `docs/frontend/state-machine.md`
- `e2e/main-analysis-approval.mock.spec.ts`
- `contracts/01-frontend-java/frontend-types.ts`

## Layout Direction

Use a Gemini-inspired conversational shell:

- left sidebar for campaign history and prior briefs
- central reasoning stream for CSV import, agent progress, signals, hypotheses, and evidence
- right action panel for experiment draft editing and approval
- bottom composer for user instructions and future chat-based edits

Do not copy a pure chat layout. The experiment plan and approval action are first-class product surfaces, not text hidden inside message bubbles.

## Primary Desktop Layout

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ Top Bar: LaunchPilot / Campaign / Run Status                              │
├────────────────┬───────────────────────────────────┬─────────────────────┤
│ Sidebar        │ Main Reasoning Stream             │ Action Panel        │
│                │                                   │                     │
│ Campaigns      │ CSV import and analysis progress  │ Experiment Draft    │
│ Prior Briefs   │ Signals                           │ Editable Fields     │
│ Lineage        │ Hypotheses                        │ Approval Summary    │
│                │ Evidence snippets                 │ Approve Button      │
├────────────────┴───────────────────────────────────┴─────────────────────┤
│ Composer: chat instructions, draft edits, continuation commands           │
└────────────────────────────────────────────────────────────────────────────┘
```

Recommended desktop grid:

- left sidebar: 240-280px
- main stream: flexible `minmax(420px, 1fr)`
- right action panel: 360-420px
- bottom composer: full width, sticky to the bottom of the app shell

## Region Responsibilities

| Region | Responsibility | States |
| --- | --- | --- |
| Top Bar | Product identity, campaign name, run status, lightweight reset/new analysis action. | All states |
| Sidebar | Campaign list, prior approved briefs, selected `parent_brief_id`, lineage entry points. | `idle`, `approved`, `restore_selecting`, `restored_context` |
| Main Reasoning Stream | CSV selection, import progress, agent progress, signals, hypotheses, evidence, continuity context. | `idle` through `waiting_for_approval`, restore states |
| Action Panel | Experiment plan draft, editable title/fields, approval validation, approval status. | `waiting_for_approval`, `editing_plan`, `approving`, `approved` |
| Composer | Natural-language commands such as changing hooks, continuing from a brief, or future experiment selection. | MVP visible but command handling may be limited |

## State To Screen Mapping

| State | Primary Visual Treatment | Required Content |
| --- | --- | --- |
| `idle` | Empty War Room with CSV input in main stream. | CSV file input labeled `CSV`, disabled or secondary Analyze button. |
| `csv_selected` | Main stream shows selected file and primary `Analyze`. | File name, campaign/date context, one primary Analyze button. |
| `importing_csv` | Main stream progress row. | Importing/indexing copy distinct from agent reasoning. |
| `import_succeeded` | Usually transient for MVP. | May briefly show imported row count before analysis starts. |
| `starting_analysis` | Main stream status row. | Starting analysis copy and non-blocking spinner. |
| `analysis_pending` | Main stream status row. | Agent run ID or short status. |
| `analysis_running` | Main stream active reasoning feed. | Text matching `Analyzing`, `Running evidence`, or `Searching evidence`; tool logs when available. |
| `waiting_for_approval` | Full three-region workroom. | Signals/hypotheses in main stream; editable experiment title in action panel; Approve button. |
| `editing_plan` | Same as review state with dirty indication. | Local draft edits visible; approval still available. |
| `approving` | Action panel locks editing. | Persistence progress and disabled approval controls. |
| `approved` | Confirmation mode. | Edited experiment title, approval/calendar confirmation, continue-from-brief affordance. |
| `restore_selecting` | Sidebar/main continuity selection. | Selected prior brief ID and continue action. |
| `restoring_context` | Main stream restoration progress. | Loading lineage copy. |
| `restored_context` | Continuity workroom. | Previous hypothesis, previous approved action, observed result, next analysis prompt. |

## MVP Interaction Model

### Analyze

After CSV selection, the visible primary action is one `Analyze` button.

The UI dispatches:

1. `IMPORT_REQUESTED`
2. `IMPORT_SUCCEEDED`
3. `RUN_AGENT_REQUESTED`

The user should not have to click a separate import button in the MVP.

### Review And Edit

When the agent reaches `WAITING_FOR_APPROVAL`:

- main stream renders signals, hypotheses, and evidence snippets
- action panel renders the experiment draft
- the title field must be an accessible textbox named `Experiment title` or `Title`
- local edits update `draftExperiments`, not the immutable original payload

### Approval

The action panel owns approval.

The primary approval button must be named `Approve` or `Approve Experiments`. MVP approval includes all visible draft experiments by default. Dedicated checkbox selection is deferred because experiment selection can later be expressed through the composer/chat command model.

### Continuation

Continuation preserves campaign linearity.

The UI must show this chain when continuing from a prior approved brief:

1. previous hypothesis
2. approved action or experiment
3. observed result or metric outcome
4. next analysis prompt

The next `RUN_AGENT_REQUESTED` must include `parent_brief_id`.

## Visual System

Reference: [`awesome-design-md/design-md/apple/DESIGN.md`](https://github.com/VoltAgent/awesome-design-md/blob/main/design-md/apple/DESIGN.md)

Translate the Apple-inspired reference into a precise workroom:

- use white, off-white, pearl, and near-black surfaces
- use one quiet blue for primary actions and links
- keep UI chrome restrained so evidence and experiment drafts dominate
- prefer crisp typography, generous spacing, and clear hierarchy
- avoid marketing hero layouts, decorative gradients, heavy shadows, and nested cards
- keep panels flat and functional; use cards only for repeated data items or modals

## Responsive Behavior

Desktop is the MVP-first target.

For tablet and mobile:

- sidebar collapses behind a navigation button
- action panel becomes a tab or bottom sheet
- main reasoning stream remains the default view
- composer remains sticky at the bottom
- approval controls must remain reachable without horizontal scrolling

## Implementation Notes

- Keep the app shell as the first screen; do not build a landing page.
- Effects should observe state changes and call APIs; reducers should remain pure.
- Fixture-backed Playwright tests define the first acceptance target.
- The first frontend implementation should optimize for passing the happy-path E2E test before adding failure and retry screens.
