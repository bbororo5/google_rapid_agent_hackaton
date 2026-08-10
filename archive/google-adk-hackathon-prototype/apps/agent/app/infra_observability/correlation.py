"""Log correlation context for service observability."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
import logging

_LOG_CONTEXT: ContextVar[dict[str, str]] = ContextVar("launchpilot_log_context", default={})


class CorrelationLogFilter(logging.Filter):
    """Attach Java-propagated correlation fields to LaunchPilot log records."""

    FIELDS = ("request_id", "trace_id", "thread_id", "workspace_id", "campaign_id")

    def filter(self, record: logging.LogRecord) -> bool:
        context = _LOG_CONTEXT.get()
        for field in self.FIELDS:
            setattr(record, field, context.get(field, "-"))
        return True


@contextmanager
def bind_correlation(
    *,
    request_id: str | None = None,
    trace_id: str | None = None,
    thread_id: str | None = None,
    workspace_id: str | None = None,
    campaign_id: str | None = None,
) -> Iterator[None]:
    """Bind correlation fields for logs emitted in this async task context."""

    next_context = {
        "request_id": request_id or "-",
        "trace_id": trace_id or request_id or "-",
        "thread_id": thread_id or "-",
        "workspace_id": workspace_id or "-",
        "campaign_id": campaign_id or "-",
    }
    token = _LOG_CONTEXT.set(next_context)
    try:
        yield
    finally:
        _LOG_CONTEXT.reset(token)
