"""In-memory run store + workflow event stream.

This is memory layer ① (run working memory) from docs/memory-and-db-flow.md:
volatile, per-run, gone when the process restarts. It also holds the persisted-
for-the-session workflow events with monotonic `sequence` so the WS endpoint can
replay on reconnect (contract 02 asyncapi).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional

from app.contracts import (
    AgentDiagnostics,
    AgentResultPayload,
    AgentRunStatus,
    AgentWorkflowEvent,
    InternalAgentRunRequest,
    InternalAgentRunStatusResponse,
    ToolCallLog,
)
from app.ids import now_iso, trace_id


def _fingerprint(req: InternalAgentRunRequest) -> str:
    # Stable hash of the request body. Used for idempotency: a re-POST with the
    # same agent_run_id must carry an identical body, else it is a 409 conflict.
    body = req.model_dump_json()
    return hashlib.sha256(body.encode()).hexdigest()


@dataclass
class RunRecord:
    """All mutable state for one agent run. Lives only in this process."""

    request: InternalAgentRunRequest
    fingerprint: str
    status: AgentRunStatus = AgentRunStatus.PENDING
    current_stage: Optional[str] = None
    retry_count: int = 0          # Class 1 tool retries (reserved; see failure.py)
    backtrack_count: int = 0      # Class 2 review-fail re-runs so far
    error_message: Optional[str] = None
    payload: Optional[AgentResultPayload] = None  # final result once review passes
    tool_call_logs: list[ToolCallLog] = field(default_factory=list)
    validator_passed: Optional[bool] = None
    phoenix_reflection_used: bool = False
    trace_id: str = field(default_factory=trace_id)
    started_at: Optional[str] = None
    updated_at: str = field(default_factory=now_iso)
    completed_at: Optional[str] = None
    cancelled: bool = False        # set by cancel REST/WS; checked between stages

    # Persisted event timeline + the next sequence number to assign.
    events: list[AgentWorkflowEvent] = field(default_factory=list)
    _seq: int = 0
    # Condition variable: lets the WS endpoint await new events without polling.
    _cond: asyncio.Condition = field(default_factory=asyncio.Condition)

    @property
    def agent_run_id(self) -> str:
        return self.request.agent_run_id

    def next_sequence(self) -> int:
        # Monotonic per-run sequence so the client can detect gaps / replay.
        self._seq += 1
        return self._seq

    async def append_event(self, event: AgentWorkflowEvent) -> None:
        # Append under the condition lock, then wake any WS streamers waiting.
        async with self._cond:
            self.events.append(event)
            self.updated_at = event.occurred_at
            self._cond.notify_all()

    def snapshot(self) -> InternalAgentRunStatusResponse:
        # Coarse GET snapshot (contract 02). Mirrors current state; no event list.
        return InternalAgentRunStatusResponse(
            agent_run_id=self.agent_run_id,
            status=self.status,
            current_stage=self.current_stage,
            retry_count=self.retry_count,
            error_message=self.error_message,
            payload=self.payload,
            tool_call_logs=self.tool_call_logs,
            agent_diagnostics=AgentDiagnostics(
                worker=None,
                validator_passed=self.validator_passed,
                backtrack_count=self.backtrack_count,
                phoenix_reflection_used=self.phoenix_reflection_used,
                trace_id=self.trace_id,
            ),
            started_at=self.started_at,
            updated_at=self.updated_at,
            completed_at=self.completed_at,
        )

    async def stream_from(self, sent: int) -> tuple[list[AgentWorkflowEvent], bool]:
        """Block until there are events past `sent` or the run is terminal.

        Returns the new slice plus whether the run has reached a terminal state,
        so the WS sender knows when to stop looping.
        """
        async with self._cond:
            while len(self.events) <= sent and not self.is_terminal():
                await self._cond.wait()
            return self.events[sent:], self.is_terminal()

    def is_terminal(self) -> bool:
        # WAITING_FOR_APPROVAL counts as terminal for the stream: Python's job is
        # done and Java owns the approval gate from here.
        return self.status in (
            AgentRunStatus.SUCCESS,
            AgentRunStatus.WAITING_FOR_APPROVAL,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        )


class RunIdConflict(Exception):
    """Same agent_run_id started with a different request body (HTTP 409)."""


class RunStore:
    """Process-wide registry of runs keyed by agent_run_id."""

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}

    def create(self, req: InternalAgentRunRequest) -> RunRecord:
        fp = _fingerprint(req)
        existing = self._runs.get(req.agent_run_id)
        if existing is not None:
            # Idempotent re-POST: same body returns the same record, different
            # body is a conflict (Java generated the id, so reuse must match).
            if existing.fingerprint != fp:
                raise RunIdConflict(req.agent_run_id)
            return existing
        record = RunRecord(request=req, fingerprint=fp)
        self._runs[req.agent_run_id] = record
        return record

    def get(self, agent_run_id: str) -> Optional[RunRecord]:
        return self._runs.get(agent_run_id)


# Single shared store for the app process (the API and orchestrator both use it).
STORE = RunStore()
