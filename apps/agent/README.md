# LaunchPilot Agent Service (Python)

FastAPI + Google ADK. Java sends free-form user turns to Python Agent Core;
Python interprets each turn into `StateDeltaProposal`, applies the deterministic
reducer, and executes at most one requested workflow phase per user round.

The service is intentionally real-integration first:

- LLM: Gemini through Google ADK, via Vertex ADC or `GEMINI_API_KEY`.
- Evidence: Elastic-backed campaign data through direct ES or Elastic MCP.
- Runtime state: Elastic runtime repository when configured, with in-memory only
  as a local contract implementation for tests.

There is no local worker or evidence fallback. Missing Gemini or Elastic config
must surface as an explicit error instead of silently producing synthetic output.

## What Maps To What

| Design | Code |
|---|---|
| Orchestrator v2 design | `docs/architecture/agent-core-v2-design.md` |
| State + reducer | `app/runtime/state.py` |
| Runtime repository | `app/runtime/repository.py` |
| ADK workers | `app/agents/adk_agents.py`, `app/agents/workers.py` |
| Turn interpreter | `app/agents/instructions.py`, `app/agents/output_schemas.py` |
| Evidence tools | `app/tools/evidence.py` |
| Reviewer gate | `app/agents/reviewer.py` |
| Turn API + WS | `app/api/turns.py`, `app/api/thread_stream.py` |

## Workflow Shape

The orchestrator is round-based:

- Analysis request -> analyst only -> signal artifacts.
- Hypothesis request -> strategist only -> hypothesis artifacts.
- Planning request -> writer + reviewer -> approval gate.
- Approval/reject/cancel structured actions are Java-owned and do not reach the
  probabilistic agent core.

## Run

```bash
cd apps/agent
uv run --with-editable . uvicorn app.main:app --port 8000
```

Health:

```bash
curl http://localhost:8000/health
```

`llm` and `evidence` should report `gemini` and `elastic`. A `missing` value is
a configuration error for real runs.

## Validation

Python contract conformance remains a lightweight local check. Full product
validation is the repo-root Playwright real-stack E2E:

```bash
npm run test:contracts
npm run test:scenarios
E2E_ENV_FILE=.env npm run test:e2e:real
```
