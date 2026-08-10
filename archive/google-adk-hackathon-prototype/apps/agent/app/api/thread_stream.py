"""Block stream WebSocket (contract 02 asyncapi.yaml).

Java connects to /internal/agent/threads/{thread_id}/stream once per thread
(before the first turn). Python replays all blocks committed so far (monotonic
sequence), then streams live ones as turns are processed.

The stream is subscribe-only: turns arrive via REST (turns.py), not this socket.
A reader task only watches for disconnect so the sender can be torn down.
"""
from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.runtime.thread_store import STORE

router = APIRouter()

_THREAD_RE = re.compile(r"^thread_[A-Za-z0-9_]+$")


async def _send_blocks(ws: WebSocket, record) -> None:
    # `sent` tracks how many messages we've delivered. stream_from blocks until
    # there are new ones, so this never busy-loops and never self-terminates.
    sent = 0
    while True:
        new = await record.stream_from(sent)
        for message in new:
            await ws.send_text(message.model_dump_json())
        sent += len(new)


async def _watch_disconnect(ws: WebSocket) -> None:
    # Subscribe-only: drain anything inbound so a client close is detected.
    while True:
        await ws.receive_text()


@router.websocket("/internal/agent/threads/{thread_id}/stream")
async def stream(ws: WebSocket, thread_id: str) -> None:
    if not _THREAD_RE.match(thread_id):
        await ws.close(code=4404)  # malformed thread id
        return
    # Create the thread on connect so blocks have somewhere to land even if the
    # WS opens before the first turn (Java's connect-then-turn order).
    record = STORE.get_or_create(thread_id)
    await ws.accept()
    sender = asyncio.create_task(_send_blocks(ws, record))
    reader = asyncio.create_task(_watch_disconnect(ws))
    try:
        # Either task ending (disconnect or error) tears down the connection.
        done, _ = await asyncio.wait({sender, reader}, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        sender.cancel()
        reader.cancel()
        try:
            await ws.close()
        except RuntimeError:
            pass
