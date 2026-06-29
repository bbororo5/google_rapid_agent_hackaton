"""Bridge Java turn trace context into Agent Core telemetry."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any

from app.observability import bind_correlation
from app.telemetry.metadata import trace_metadata


@dataclass(frozen=True, slots=True)
class AgentTraceContext:
    """Trace context propagated from Java for one accepted user turn."""

    request_id: str
    source: str
    otel_trace_id: str | None = None

    @classmethod
    def from_turn(cls, turn) -> "AgentTraceContext":
        trace = turn.trace_context
        if trace is None:
            return cls(request_id="req_unknown", source="unknown")
        return cls(
            request_id=trace.request_id,
            source=trace.source,
            otel_trace_id=trace.otel_trace_id,
        )

    @property
    def log_trace_id(self) -> str:
        return self.otel_trace_id or self.request_id

    def bind_logs(
        self,
        *,
        thread_id: str,
        workspace_id: str | None,
        campaign_id: str | None,
    ) -> AbstractContextManager[None]:
        return bind_correlation(
            request_id=self.request_id,
            trace_id=self.log_trace_id,
            thread_id=thread_id,
            workspace_id=workspace_id,
            campaign_id=campaign_id,
        )

    def metadata(
        self,
        *,
        thread_id: str,
        workspace_id: str | None,
        campaign_id: str | None,
    ) -> dict[str, Any]:
        return trace_metadata(
            request_id=self.request_id,
            trace_id=self.log_trace_id,
            trace_source=self.source,
            thread_id=thread_id,
            workspace_id=workspace_id,
            campaign_id=campaign_id,
            otel_trace_id=self.otel_trace_id,
        )
