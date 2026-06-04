# LaunchPilot Agent Service (Python)

FastAPI + Google ADK. Implements the **golden path** (mode M3: fixed 4 workers
analyst -> strategist -> writer -> reviewer) behind the internal contract that
Java calls. Built contract-first: the Pydantic models in `app/contracts/` are a
faithful translation of `contracts/02` (run API + workflow stream) and
`contracts/05` (worker outputs), and the test suite validates the shipped
contract example JSONs against them.

## Two modes (auto-derived, no flag)

| | real | stub (default offline) |
|---|---|---|
| **LLM** | ADK on Vertex AI (ADC) when `GOOGLE_GENAI_USE_VERTEXAI=TRUE` + `GOOGLE_CLOUD_PROJECT` set, or AI Studio when `GEMINI_API_KEY` set | deterministic workers |
| **Evidence** | Elastic MCP when `ELASTIC_MCP_URL` set | seeded BTS demo data |

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
| 4 workers (agent-tool-spec §1) | `app/agents/` (stub.py + adk_agents.py) |
| Evidence tools (contract 04) | `app/tools/evidence.py` |
| Run working memory ① (memory-and-db-flow) | `app/runtime/store.py` (session state) |
| Reviewer gate + issue codes (§3-C/§4) | `app/agents/reviewer.py` |
| Formatter = Python normalization (§6) | `app/agents/formatter.py` |
| Backtracking routing (§4-B) | `app/agents/failure.py` |
| Run API + WS (contract 02) | `app/api/runs.py`, `app/api/stream.py` |

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

- `test_contract_conformance.py` — contract example JSONs validate against the models.
- `test_golden_path.py` — orchestrator reaches WAITING_FOR_APPROVAL with a valid payload.
- `test_api.py` — REST 202 + WS replay + snapshot + 404/409 contract errors.

## Known stubs (documented gaps, not blockers)

- `team_notes` served from seed; real seed source TBD.
- `parent_brief_id` continuity (R12/R13) is a no-op.
- Phoenix/Arize reflection read is stubbed; tracing export is guarded/optional.
- Question-based routing (M1/M2) deferred — always runs the full pipeline.
- Real Elastic MCP calls (`app/tools/mcp_client.py`) raise until wired.
- Signal thresholds (2.0/1.3) are unverified placeholders.
