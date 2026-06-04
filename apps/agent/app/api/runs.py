"""REST run API (contract 02 openapi.yaml).

Three endpoints Java calls: start a run, fetch a coarse snapshot, cancel. The
live event stream is the WS endpoint in stream.py.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app import orchestrator
from app.contracts import (
    ErrorBody,
    ErrorCode,
    ErrorResponse,
    InternalAgentRunAcceptedResponse,
    InternalAgentRunCancelledResponse,
    InternalAgentRunRequest,
)
from app.ids import now_iso
from app.runtime.store import STORE, RunIdConflict

router = APIRouter(prefix="/internal/agent")


def _error(status: int, code: ErrorCode, message: str, request_id: str = "req_unknown") -> JSONResponse:
    # Build the exact contract error envelope (ok:false + error body) rather than
    # FastAPI's default {"detail": ...}, so Java sees the agreed shape.
    body = ErrorResponse(ok=False, error=ErrorBody(code=code, message=message, request_id=request_id))
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


@router.post("/runs", status_code=202)
async def start_run(request: Request):
    # Validate the body against the contract model before doing anything.
    raw = await request.json()
    try:
        req = InternalAgentRunRequest(**raw)
    except ValidationError as exc:
        return _error(400, ErrorCode.INVALID_REQUEST, exc.errors().__str__())

    # Register the run. Re-POSTing the same id+body is idempotent; a different
    # body for the same id is a 409 (Java owns id generation).
    try:
        record = STORE.create(req)
    except RunIdConflict:
        return _error(
            409, ErrorCode.RUN_ID_CONFLICT, "run id reused with a different body",
            req.trace_context.request_id,
        )

    # Kick off the pipeline in the background only on first creation. The HTTP
    # response returns immediately (202); progress arrives over the WS stream.
    if record.started_at is None and not record.events:
        asyncio.create_task(orchestrator.execute(record))

    rid = req.agent_run_id
    resp = InternalAgentRunAcceptedResponse(
        ok=True,
        agent_run_id=rid,
        status="PENDING",
        stream_url=f"/internal/agent/runs/{rid}/stream",
        snapshot_url=f"/internal/agent/runs/{rid}",
        accepted_at=now_iso(),
    )
    return JSONResponse(status_code=202, content=resp.model_dump(mode="json"))


@router.get("/runs/{agent_run_id}")
async def get_run(agent_run_id: str):
    # Coarse snapshot for reconnect/recovery (no event history; that's the WS).
    record = STORE.get(agent_run_id)
    if record is None:
        return _error(404, ErrorCode.RUN_NOT_FOUND, f"run {agent_run_id} not found")
    return JSONResponse(status_code=200, content=record.snapshot().model_dump(mode="json"))


@router.post("/runs/{agent_run_id}/cancel", status_code=202)
async def cancel_run(agent_run_id: str):
    # Best-effort cancel: flag the run; the orchestrator stops at the next stage
    # boundary and emits run.cancelled.
    record = STORE.get(agent_run_id)
    if record is None:
        return _error(404, ErrorCode.RUN_NOT_FOUND, f"run {agent_run_id} not found")
    record.cancelled = True
    async with record._cond:  # wake the stream / orchestrator waiters
        record._cond.notify_all()
    resp = InternalAgentRunCancelledResponse(
        ok=True, agent_run_id=agent_run_id, status="CANCELLED", cancelled_at=now_iso()
    )
    return JSONResponse(status_code=202, content=resp.model_dump(mode="json"))
