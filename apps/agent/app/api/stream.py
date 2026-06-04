"""Workflow event WebSocket (contract 02 asyncapi.yaml).

Java connects to /internal/agent/runs/{id}/stream. Python:
- replays all events so far (monotonic sequence), then streams live ones;
- accepts InternalAgentCommand (run.cancel) from Java.

Two concurrent tasks run per connection: one sends events out, one reads
commands in. The connection closes when the run reaches a terminal state.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.contracts import InternalAgentCommand
from app.runtime.store import STORE

router = APIRouter()


async def _send_events(ws: WebSocket, record) -> None:
    # `sent` tracks how many events we've already delivered. stream_from blocks
    # until there are new ones (or the run is terminal), so this never busy-loops.
    sent = 0
    while True:
        new, terminal = await record.stream_from(sent)
        for event in new:
            await ws.send_text(event.model_dump_json())
        sent += len(new)
        # Stop once terminal AND we've flushed every event up to the end.
        if terminal and sent >= len(record.events):
            return


async def _read_commands(ws: WebSocket, record) -> None:
    # Inbound channel: Java may send run.cancel while the run is active.
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
        await ws.close(code=4404)  # unknown run
        return
    await ws.accept()
    sender = asyncio.create_task(_send_events(ws, record))
    reader = asyncio.create_task(_read_commands(ws, record))
    try:
        # The sender drives the lifetime: it returns when the run is terminal.
        await sender
    except WebSocketDisconnect:
        pass
    finally:
        # Tear down the partner task and close cleanly regardless of how we got here.
        reader.cancel()
        sender.cancel()
        try:
            await ws.close()
        except RuntimeError:
            pass
