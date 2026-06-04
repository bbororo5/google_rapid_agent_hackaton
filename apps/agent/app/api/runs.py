"""REST run API (contract 02 openapi.yaml)."""
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
    body = ErrorResponse(ok=False, error=ErrorBody(code=code, message=message, request_id=request_id))
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


@router.post("/runs", status_code=202)
async def start_run(request: Request):
    raw = await request.json()
    try:
        req = InternalAgentRunRequest(**raw)
    except ValidationError as exc:
        return _error(400, ErrorCode.INVALID_REQUEST, exc.errors().__str__())

    try:
        record = STORE.create(req)
    except RunIdConflict:
        return _error(
            409, ErrorCode.RUN_ID_CONFLICT, "run id reused with a different body",
            req.trace_context.request_id,
        )

    # Launch the pipeline only on first creation (idempotent re-POST is a no-op).
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
    record = STORE.get(agent_run_id)
    if record is None:
        return _error(404, ErrorCode.RUN_NOT_FOUND, f"run {agent_run_id} not found")
    return JSONResponse(status_code=200, content=record.snapshot().model_dump(mode="json"))


@router.post("/runs/{agent_run_id}/cancel", status_code=202)
async def cancel_run(agent_run_id: str):
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
