# Playwright E2E Tests

These tests are executable acceptance criteria for the conversation-first agent experience.

The real-stack suite is intentionally small. It covers only the core user journey
through the full architecture:

- Playwright browser -> Next.js frontend container
- Frontend -> Java backend container
- Java -> Python Agent Core container
- Python -> real Gemini/Google ADK
- Java/Python -> real Elastic
- Optional Phoenix export when `PHOENIX_API_KEY` is set
- CSV demo happy path from upload to approved growth brief
- Target round-based workflow for the orchestrator refactor

Useful commands:

```sh
npm run test:e2e:list
E2E_ENV_FILE=s.env npm run test:e2e:real
E2E_ROUND_BASED_ACTIVE=true E2E_ENV_FILE=s.env npm run test:e2e:rounds
npm run test:e2e:ui
```

`test:e2e:real` runs `tools/e2e-preflight.mjs` first. It fails fast unless the
selected env file contains real Gemini/Vertex credentials and real Elastic
credentials. This prevents accidentally treating stub/offline mode as full E2E.

By default Playwright starts a fresh `docker compose --env-file <env> up --build`
stack. Set `PLAYWRIGHT_REUSE_SERVER=true` only when intentionally reusing an
already-running stack during local debugging.

`real-round-based-workflow.spec.ts` is the acceptance spec for the next
orchestrator refactor. It is skipped unless `E2E_ROUND_BASED_ACTIVE=true`
because the current implementation still runs a one-shot monolithic happy path.
