"""In-memory live thread store + block message stream.

This is not the durable Agent Core runtime repository. It holds the live
WebSocket block timeline and process-local ThreadRecord handles. Durable
workflow state is represented by SharedStateVector and committed through
app.runtime.repository.

A thread is long-lived: many turns, no terminal state. The WS sender streams
forever until the socket closes.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional

from app.contracts import InternalStreamMessage
from app.runtime.state import SharedStateVector


@dataclass
class ThreadRecord:
    """All mutable state for one conversation thread. Lives only in this process."""

    thread_id: str
    workspace_id: Optional[str] = None
    campaign_id: Optional[str] = None
    cancelled: bool = False
    state: SharedStateVector = field(default_factory=SharedStateVector)
    turn_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    messages: list[InternalStreamMessage] = field(default_factory=list)
    _seq: int = 0
    _cond: asyncio.Condition = field(default_factory=asyncio.Condition)

    def set_context(self, workspace_id: Optional[str], campaign_id: Optional[str]) -> None:
        # Filled from the first turn that carries them (the WS may connect first).
        if workspace_id:
            self.workspace_id = workspace_id
        if campaign_id:
            self.campaign_id = campaign_id

    def next_sequence(self) -> int:
        # Monotonic per-thread sequence so the client can detect gaps / replay.
        self._seq += 1
        return self._seq

    async def append(self, message: InternalStreamMessage) -> None:
        # Append under the condition lock, then wake any WS streamers waiting.
        async with self._cond:
            self.messages.append(message)
            self._cond.notify_all()

    async def stream_from(self, sent: int) -> list[InternalStreamMessage]:
        """Block until there are messages past `sent`, then return the new slice.

        Never returns "terminal": a thread stays open for its whole lifetime, so
        the WS sender loops on this until the socket disconnects.
        """
        async with self._cond:
            while len(self.messages) <= sent:
                await self._cond.wait()
            return self.messages[sent:]


class ThreadStore:
    """Process-wide registry of threads keyed by thread_id."""

    def __init__(self) -> None:
        self._threads: dict[str, ThreadRecord] = {}

    def get_or_create(self, thread_id: str) -> ThreadRecord:
        record = self._threads.get(thread_id)
        if record is None:
            record = ThreadRecord(thread_id=thread_id)
            self._threads[thread_id] = record
        return record

    def get(self, thread_id: str) -> Optional[ThreadRecord]:
        return self._threads.get(thread_id)


# Single shared store for the app process (the API and orchestrator both use it).
STORE = ThreadStore()
