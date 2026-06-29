"""Tracing init (memory layer 4 — write side, Arize track).

OpenInference -> Phoenix Cloud. Gated on PHOENIX_API_KEY so a missing key (or
missing packages) is a no-op. `register(auto_instrument=True)` discovers the
installed openinference-instrumentation-google-adk and traces every ADK LLM +
tool span automatically. Matches the official Arize gemini-hackathon example.

This is the WRITE half of layer ④: the agent exports its run spans for later
inspection (and for the Phoenix MCP read side in app/agents/reflection.py).
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import logging
from collections.abc import Iterator

# Use the launchpilot.* namespace so these lines actually surface in the
# container logs (the app configures logging for launchpilot.*, not app.*).
log = logging.getLogger("launchpilot.observability")

_provider = None
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


def init_tracing():
    """Register Phoenix tracing once. Returns the provider, or None if disabled."""
    global _provider
    if _provider is not None:
        return _provider

    from app.config import get_settings

    settings = get_settings()
    # Gate on the API key (the example does the same): no key -> tracing off.
    if not settings.phoenix_api_key:
        return None
    try:
        # Lazy import: optional extras (pip install .[observability]).
        # register() reads PHOENIX_COLLECTOR_ENDPOINT + PHOENIX_API_KEY from env
        # and auto-attaches the auth header.
        from phoenix.otel import register

        # Pass the OTLP HTTP traces endpoint explicitly. Without this, register()
        # cannot infer the protocol from the bare space URL and warns
        # ("Could not infer collector endpoint protocol, defaulting to HTTP"),
        # which can send spans to the wrong path. Phoenix Cloud's OTLP HTTP path
        # is <collector_endpoint>/v1/traces; the api-key header comes from
        # PHOENIX_API_KEY / OTEL_EXPORTER_OTLP_HEADERS in the env.
        kwargs = dict(
            project_name=settings.phoenix_project,
            batch=False,            # flush eagerly (short-lived runs)
            auto_instrument=True,   # hook the installed ADK instrumentor
            verbose=False,
        )
        endpoint = None
        if settings.phoenix_endpoint:
            base = settings.phoenix_endpoint.rstrip("/")
            endpoint = base if base.endswith("/v1/traces") else f"{base}/v1/traces"
            kwargs["endpoint"] = endpoint
            kwargs["protocol"] = "http/protobuf"

        _provider = register(**kwargs)
        log.info("Phoenix tracing enabled (project=%s endpoint=%s)",
                 settings.phoenix_project, endpoint or "<env-default>")
        return _provider
    except Exception as exc:  # noqa: BLE001 - tracing must never break the app
        log.warning("Phoenix tracing disabled: %s", exc)
        return None
