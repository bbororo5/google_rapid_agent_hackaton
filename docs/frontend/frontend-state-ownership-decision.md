# Frontend State Ownership

Status: current conversation-first design.

The frontend should model the product as a conversation workspace, not as a backend process state machine.

## Ownership

| State | Owner |
| --- | --- |
| Composer text, selected CSV, local edits | Frontend feature controller |
| WebSocket connection health | Stream adapter |
| Agent messages and blocks | Feature reducer/projection |
| Right panel open state and selected document/artifact/approval | Frontend UI state derived from blocks |
| Agent reasoning/tool state | Agent Core, exposed only as blocks |

## UI Rule

React components should consume a ViewModel shaped around screen needs:

```ts
interface ExperimentPlannerViewModel {
  composer: PlannerComposerView;
  thread: PlannerThreadView;
  rightPanel: PlannerRightPanelView;
  progress: PlannerProgressView;
  approval: PlannerApprovalView;
  commands: PlannerCommands;
}
```

Components should not depend on internal backend stages. They should render messages and react to block kinds.

## Contract Rule

User intent leaves the frontend as `message.send`. Button clicks may include an optional action hint, but they are still sent as the same command shape.

Server output arrives as `StreamMessage.blocks[]`. The block vocabulary is the stable UI contract.
