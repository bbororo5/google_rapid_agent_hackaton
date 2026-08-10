# Scenarios

The old contract-scenario JSON files were removed with the run-based contract.

Current end-to-end behavior is covered by executable Playwright scenarios:

- `contracts/01-frontend-java`: public conversation stream contract.
- `contracts/02-java-python-agent`: internal Agent Core turn and stream contract.
- `e2e/conversation-first.mock.spec.ts`: free chat, document blocks, signal/approval blocks, natural approval, ordering, and composer behavior.
- `e2e/main-analysis-approval.mock.spec.ts`: mock browser flow using `message.send` and `StreamMessage.blocks[]`.

`npm run test:scenarios` verifies that these conversation-first acceptance scenarios and contract markers are present. The old run-based `.scenario.json` files are intentionally absent.

Keep future scenarios conversation-first: user messages drive the flow, and specialized UI behavior comes from received block kinds.
