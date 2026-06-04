"""Workflow event WebSocket (contract 02 asyncapi.yaml).

Java connects to /internal/agent/runs/{id}/stream. Python:
- replays all events so far (monotonic sequence), then streams live ones;
- accepts InternalAgentCommand (run.cancel) from Java.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.contracts import InternalAgentCommand
from app.runtime.store import STORE

router = APIRouter()


async def _send_events(ws: WebSocket, record) -> None:
    sent = 0
    while True:
        new, terminal = await record.stream_from(sent)
        for event in new:
            await ws.send_text(event.model_dump_json())
        sent += len(new)
        if terminal and sent >= len(record.events):
            return


async def _read_commands(ws: WebSocket, record) -> None:
    while True:
        raw = await ws.receive_json()
        try:
            command = InternalAgentCommand(**raw)
        except Exception:  # noqa: BLE001 - ignore malformed commands
            continue
        if command.type.value == "run.cancel":
            record.cancelled = True
            async with record._cond:
                record._cond.notify_all()


@router.websocket("/internal/agent/runs/{agent_run_id}/stream")
async def stream(ws: WebSocket, agent_run_id: str) -> None:
    record = STORE.get(agent_run_id)
    if record is None:
        await ws.close(code=4404)
        return
    await ws.accept()
    sender = asyncio.create_task(_send_events(ws, record))
    reader = asyncio.create_task(_read_commands(ws, record))
    try:
        await sender  # finishes when the run is terminal
    except WebSocketDisconnect:
        pass
    finally:
        reader.cancel()
        sender.cancel()
        try:
            await ws.close()
        except RuntimeError:
            pass
