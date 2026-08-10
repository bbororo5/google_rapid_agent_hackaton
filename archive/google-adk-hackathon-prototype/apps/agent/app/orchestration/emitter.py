"""User-safe stream emission helpers for orchestration objects."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.runtime import blocks
from app.runtime.thread_store import ThreadRecord


class StreamEmitter:
    """Small object facade over contract-shaped stream blocks."""

    async def progress(
        self,
        record: ThreadRecord,
        activity_id: str,
        title: str,
        status: str,
        detail: str | None = None,
    ) -> None:
        await blocks.assistant(record, [blocks.activity_block(activity_id, title, status, detail)])

    @asynccontextmanager
    async def activity(
        self,
        record: ThreadRecord,
        activity_id: str,
        running_title: str,
        done_title: str | None = None,
        detail: str | None = None,
    ) -> AsyncIterator[None]:
        await self.progress(record, activity_id, running_title, "running", detail)
        try:
            yield
        except Exception:
            await self.progress(record, activity_id, running_title, "failed")
            raise
        else:
            await self.progress(record, activity_id, done_title or running_title, "done", detail)

    async def assistant_text(self, record: ThreadRecord, text: str) -> None:
        await blocks.assistant(record, [blocks.text_block(text)])

    async def assistant_blocks(self, record: ThreadRecord, block_list: list[dict]) -> None:
        await blocks.assistant(record, block_list)

    async def system_error(
        self,
        record: ThreadRecord,
        title: str,
        detail: str,
        retryable: bool = True,
    ) -> None:
        await blocks.system(record, [blocks.error_block(title, detail, retryable=retryable)])

    async def system_result(self, record: ThreadRecord, title: str, detail: str | None = None) -> None:
        await blocks.system(record, [blocks.result_block(title, detail)])
