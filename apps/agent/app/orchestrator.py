"""Thin entrypoint for the object-oriented Agent Core turn workflow."""

from __future__ import annotations

from app.orchestration import TurnWorkflow
from app.runtime.thread_store import ThreadRecord

_workflow = TurnWorkflow()


async def process_turn(
    record: ThreadRecord,
    content: str,
    attachments: tuple = (),
) -> None:
    """Handle one user turn while preserving the public orchestrator API."""
    async with record.turn_lock:
        await _workflow.run(record, content, attachments)
