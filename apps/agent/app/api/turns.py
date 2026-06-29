"""REST turn API (contract 02 openapi.yaml).

Java posts a user turn here; Python accepts it (202) and processes it in the
background, streaming user-safe blocks over the WS endpoint in thread_stream.py.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app import orchestrator
from app.contracts import (
    ErrorBody,
    ErrorCode,
    ErrorResponse,
    InternalAgentTurn,
    InternalAgentTurnAccepted,
)
from app.ids import now_iso
from app.observability import bind_correlation
from app.runtime.thread_store import STORE

router = APIRouter(prefix="/internal/agent")
log = logging.getLogger("launchpilot.turns")


def _error(status: int, code: ErrorCode, message: str, request_id: str = "req_unknown") -> JSONResponse:
    # Build the exact contract error envelope (ok:false + error body) rather than
    # FastAPI's default {"detail": ...}, so Java sees the agreed shape.
    body = ErrorResponse(ok=False, error=ErrorBody(code=code, message=message, request_id=request_id))
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


@router.post("/turns", status_code=202)
async def send_turn(request: Request):
    # Validate the body against the contract model before doing anything.
    raw = await request.json()
    try:
        turn = InternalAgentTurn(**raw)
    except ValidationError as exc:
        log.warning("turn rejected (400): %s", exc.errors())
        return _error(400, ErrorCode.INVALID_REQUEST, exc.errors().__str__())

    trace = turn.trace_context
    request_id = trace.request_id if trace else "req_unknown"
    trace_id = trace.otel_trace_id if trace and trace.otel_trace_id else request_id

    with bind_correlation(
        request_id=request_id,
        trace_id=trace_id,
        thread_id=turn.thread_id,
        workspace_id=turn.workspace_id,
        campaign_id=turn.campaign_id,
    ):
        log.info("POST /turns thread=%s ws=%s camp=%s content=%r",
                 turn.thread_id, turn.workspace_id, turn.campaign_id, turn.content[:80])

        # Get/create the thread (the WS may have created it already on connect) and
        # fill its workspace/campaign context from this turn.
        record = STORE.get_or_create(turn.thread_id)
        record.set_context(turn.workspace_id, turn.campaign_id)

        # Process the turn in the background; blocks arrive over the WS stream.
        asyncio.create_task(orchestrator.process_turn(record, turn.content, tuple(turn.attachments)))

        resp = InternalAgentTurnAccepted(ok=True, thread_id=turn.thread_id, accepted_at=now_iso())
        return JSONResponse(status_code=202, content=resp.model_dump(mode="json"))
