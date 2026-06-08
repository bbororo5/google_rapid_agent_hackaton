"""FastAPI app for the LaunchPilot Python Agent Service.

Serves the internal contract-02 API (REST + WS) that Java calls. This is a
custom app (not ADK's get_fast_api_app) because the endpoints must match the
LaunchPilot contract, not ADK's default routes.
"""
from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import thread_stream, turns
from app.config import get_settings
from app.observability import init_tracing

# Dedicated app logger to stdout so per-stage pipeline logs show in `docker logs`
# regardless of uvicorn's own logging config. Children: launchpilot.orchestrator,
# launchpilot.turns, launchpilot.adk, etc. Filter live with:
#   docker compose logs -f agent | grep launchpilot
# Levels are env-tunable: AGENT_LOG_LEVEL (our logs, default INFO) and
# AGENT_LOG_LIBS (the underlying Gemini/HTTP libs, default WARNING). Set
# AGENT_LOG_LIBS=INFO (or DEBUG) to watch every LLM request + retry/ConnectError.
_LEVEL = os.environ.get("AGENT_LOG_LEVEL", "INFO").upper()
_LIB_LEVEL = os.environ.get("AGENT_LOG_LIBS", "WARNING").upper()
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

_app_log = logging.getLogger("launchpilot")
if not _app_log.handlers:
    _app_log.addHandler(_handler)
    _app_log.setLevel(_LEVEL)
    _app_log.propagate = False

# Surface the underlying LLM/HTTP stack on the same stream so a hung or retrying
# Gemini/Vertex call is visible instead of looking like a silent stall.
for _name in ("google_genai", "google.adk", "google.genai", "httpx", "httpcore"):
    _lib = logging.getLogger(_name)
    if _handler not in _lib.handlers:
        _lib.addHandler(_handler)
    _lib.setLevel(_LIB_LEVEL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: wire tracing if configured (no-op otherwise). Nothing to tear down.
    init_tracing()
    yield


app = FastAPI(title="LaunchPilot Agent Service", version="0.1.0", lifespan=lifespan)
app.include_router(turns.router)         # REST: POST /internal/agent/turns
app.include_router(thread_stream.router)  # WS: per-thread block stream


@app.get("/health")
async def health() -> dict:
    # Quick check of which mode each side resolved to (stub vs real).
    s = get_settings()
    return {
        "ok": True,
        "llm": "gemini" if s.use_real_llm else "stub",
        "evidence": "elastic" if s.use_real_elastic else "stub",
    }


def run() -> None:
    # Convenience entrypoint: `python -m app.main` launches uvicorn.
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=get_settings().port)


if __name__ == "__main__":
    run()
