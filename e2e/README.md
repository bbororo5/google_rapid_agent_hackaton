# Playwright E2E Tests

These tests are executable acceptance criteria for the conversation-first agent experience.

The suite is intentionally small. It covers only the core user journeys:

- Free chat, including Enter to send and Shift+Enter for multiline drafts.
- Saved markdown outputs opening as tabs in the right drawer while staying available from the thread.
- Agent-raised signal and approval outputs staying inline while also being archived.
- The CSV demo happy path from upload to approved growth brief.

Useful commands:

```sh
npm run test:e2e:list
npm run test:e2e
npm run test:e2e:ui
```
