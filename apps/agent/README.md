# LaunchPilot Agent Service (Python)

FastAPI + Google ADK. Implements the Python Agent Core behind the internal
contract that Java calls. The current Orchestrator Component uses
`StateDeltaProposal -> deterministic reducer -> delegation decision`, then either
replies directly, delegates to a phase facade, or runs the 4-worker pipeline
(`analyst -> strategist -> writer -> reviewer`).

Built contract-first: the Pydantic models in `app/contracts/` are a faithful
translation of `contracts/02` (turn API + workflow stream) and `contracts/05`
(worker outputs), while runtime state follows `contracts/07`.

## Two modes (auto-derived, no flag)

| | real | stub (default offline) |
|---|---|---|
| **LLM** | ADK on Vertex AI (ADC) when `GOOGLE_GENAI_USE_VERTEXAI=TRUE` + `GOOGLE_CLOUD_PROJECT` set, or AI Studio when `GEMINI_API_KEY` set | deterministic workers |
| **Evidence** | Direct Elastic or Elastic MCP when configured | seeded BTS demo data |
| **Runtime state** | Elastic runtime repository when `ELASTIC_URL` + `ELASTIC_API_KEY` set | in-memory repository |

Stub mode lets the whole pipeline + API + WS run and be tested without an LLM or
a live Elastic cluster.

**Vertex AI (ADC) is the recommended LLM path** — no API key in the repo. ADK
authenticates through Application Default Credentials. Set ADC up once:

```bash
gcloud auth application-default login
gcloud config set project rapid-agent-hackacthon
# then in .env: GOOGLE_GENAI_USE_VERTEXAI=TRUE, GOOGLE_CLOUD_PROJECT=rapid-agent-hackacthon
```

## What maps to what

| Design (docs) | Code |
|---|---|
| Orchestrator v2 design | `docs/architecture/agent-core-v2-design.md` |
| State + reducer | `app/runtime/state.py` |
| Runtime repository | `app/runtime/repository.py` |
| 4 workers | `app/agents/` (stub.py + adk_agents.py) |
| Evidence tools (contract 04) | `app/tools/evidence.py` |
| Reviewer gate + issue codes (§3-C/§4) | `app/agents/reviewer.py` |
| Formatter = Python normalization (§6) | `app/agents/formatter.py` |
| Backtracking routing (§4-B) | `app/agents/failure.py` |
| Turn API + WS (contract 02) | `app/api/turns.py`, `app/api/thread_stream.py` |

## Run

```bash
cd apps/agent
cp .env.example .env          # optional; leave keys blank for stub mode
uv run --with-editable . uvicorn app.main:app --port 8000
# health: GET http://localhost:8000/health
```

## Test

```bash
cd apps/agent
PYTHONPATH=. uv run --no-project \
  --with pydantic --with fastapi --with python-dotenv \
  --with pytest --with pytest-asyncio --with httpx \
  pytest -q
```

Pytest is a fast component-level safety net for the Python Agent Core. It does
not prove real Gemini/Elastic integration. Full system validation is the
Playwright real-stack E2E suite at the repo root.

- `test_contract_conformance.py` — contract example JSONs validate against the models.
- `test_golden_path.py` — scenario-driven Orchestrator Component golden paths.
- `test_api.py` — REST 202 + WS replay + snapshot + 404/409 contract errors.
- `test_evidence_scope.py` — workspace/campaign evidence boundary checks.

Full E2E:

```bash
E2E_ENV_FILE=s.env npm run test:e2e:real
```

## Known stubs (documented gaps, not blockers)

- `team_notes` served from seed; real seed source TBD.
- Phoenix/Arize reflection read is stubbed; tracing export is guarded/optional.
- Detailed phase sub-agent skill hot-swapping and artifact patch schema are deferred.
- Java-owned `agent_thread_messages` persistence is documented in contract 07; Python currently reads through the runtime repository interface.
- Signal thresholds (2.0/1.3) are unverified placeholders.
