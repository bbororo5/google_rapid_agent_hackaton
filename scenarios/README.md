# Scenarios

The old contract-scenario JSON files were removed with the run-based contract.

Current end-to-end behavior is covered by:

- `contracts/01-frontend-java`: public conversation stream contract.
- `contracts/02-java-python-agent`: internal Agent Core turn and stream contract.
- `e2e/main-analysis-approval.mock.spec.ts`: mock browser flow using `message.send` and `StreamMessage.blocks[]`.

Keep future scenarios conversation-first: user messages drive the flow, and specialized UI behavior comes from received block kinds.
