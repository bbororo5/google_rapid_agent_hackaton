"""Tracing init (memory layer 4 — write side).

OpenInference -> Phoenix/Arize, guarded so missing packages or endpoint are a
no-op. The reflection READ tools (get_traces/get_evaluations) are stubbed on the
golden path and live elsewhere.

This is the WRITE half of layer ④: the agent exports its run spans for later
inspection. It is NOT an MCP tool and never blocks the pipeline.
"""
from __future__ import annotations

import logging

from app.config import get_settings

log = logging.getLogger(__name__)


def init_tracing() -> None:
    settings = get_settings()
    # No collector configured -> tracing is simply off.
    if not settings.phoenix_endpoint:
        return
    try:
        # Imported lazily: these are optional extras (pip install .[observability]).
        from openinference.instrumentation.google_adk import GoogleADKInstrumentor
        from phoenix.otel import register

        # register() sets up the OTLP exporter; auto_instrument hooks ADK calls.
        provider = register(project_name=settings.phoenix_project, auto_instrument=True)
        GoogleADKInstrumentor().instrument(tracer_provider=provider)
        log.info("Phoenix tracing enabled (project=%s)", settings.phoenix_project)
    except Exception as exc:  # noqa: BLE001 - tracing must never break the app
        # Any setup failure (missing package, bad endpoint) degrades to no tracing.
        log.warning("Phoenix tracing disabled: %s", exc)
