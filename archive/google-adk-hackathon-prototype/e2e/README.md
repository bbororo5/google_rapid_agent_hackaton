# Playwright E2E Tests

These tests are executable acceptance criteria for the full round-based agent
experience.

The real-stack suite is intentionally small. It covers only the core user journey
through the full architecture:

- Playwright browser -> Next.js frontend container
- Frontend -> Java backend container
- Java -> Python Agent Core container
- Python -> real Gemini/Google ADK
- Java/Python -> real Elastic
- Optional Phoenix export when `PHOENIX_API_KEY` is set
- Round-based workflow for the orchestrator refactor

Useful commands:

```sh
npm run test:e2e:list
E2E_ENV_FILE=.env npm run test:e2e:real
E2E_ENV_FILE=.env npm run test:e2e:memory
npm run test:e2e:ui
```

`memory-continuity.spec.ts` is the ADR-005 runtime-memory journey (Redis hot tier
+ Elastic episodic persistence). It drives repeated backtracks and a resumed
pipeline to assert the thread stays coherent across episode checkpoints. The
stack now also starts a `redis` service (see `docker-compose.yml`).

`test:e2e` and `test:e2e:real` run the same full E2E target:
`real-round-based-workflow.spec.ts`. The command runs `tools/e2e-preflight.mjs`
first and fails fast unless the selected env file contains real Gemini/Vertex
credentials and real Elastic credentials. This prevents accidentally treating
incomplete local configuration as full E2E.

By default Playwright starts a fresh `docker compose --env-file <env> up --build`
stack. Set `PLAYWRIGHT_REUSE_SERVER=true` only when intentionally reusing an
already-running stack during local debugging.

`real-round-based-workflow.spec.ts` models the product as a series of user
rounds: free chat, CSV analysis, analysis discussion, hypothesis request,
hypothesis discussion, planning request, plan revision, approval, in-flight
discussion, post-experiment analysis, insight discussion, and backtracking from
planning to analysis.
