"""Tracing init (memory layer 4 — write side).

OpenInference -> Phoenix/Arize, guarded so missing packages or endpoint are a
no-op. The reflection READ tools (get_traces/get_evaluations) are stubbed on the
golden path and live elsewhere.
"""
from __future__ import annotations

import logging

from app.config import get_settings

log = logging.getLogger(__name__)


def init_tracing() -> None:
    settings = get_settings()
    if not settings.phoenix_endpoint:
        return
    try:
        from openinference.instrumentation.google_adk import GoogleADKInstrumentor
        from phoenix.otel import register

        provider = register(project_name=settings.phoenix_project, auto_instrument=True)
        GoogleADKInstrumentor().instrument(tracer_provider=provider)
        log.info("Phoenix tracing enabled (project=%s)", settings.phoenix_project)
    except Exception as exc:  # noqa: BLE001 - tracing must never break the app
        log.warning("Phoenix tracing disabled: %s", exc)
