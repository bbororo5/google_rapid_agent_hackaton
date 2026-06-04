"""FastAPI app for the LaunchPilot Python Agent Service.

Serves the internal contract-02 API (REST + WS) that Java calls. This is a
custom app (not ADK's get_fast_api_app) because the endpoints must match the
LaunchPilot contract, not ADK's default routes.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import runs, stream
from app.config import get_settings
from app.observability import init_tracing


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_tracing()
    yield


app = FastAPI(title="LaunchPilot Agent Service", version="0.1.0", lifespan=lifespan)
app.include_router(runs.router)
app.include_router(stream.router)


@app.get("/health")
async def health() -> dict:
    s = get_settings()
    return {
        "ok": True,
        "llm": "gemini" if s.use_real_llm else "stub",
        "evidence": "elastic-mcp" if s.use_real_elastic else "stub",
    }


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=get_settings().port)


if __name__ == "__main__":
    run()
