"""Tracing init (memory layer 4 — write side, Arize track).

OpenInference -> Phoenix Cloud. Gated on PHOENIX_API_KEY so a missing key (or
missing packages) is a no-op. `register(auto_instrument=True)` discovers the
installed openinference-instrumentation-google-adk and traces every ADK LLM +
tool span automatically. Matches the official Arize gemini-hackathon example.

This is the WRITE half of layer ④: the agent exports its run spans for later
inspection (and for the Phoenix MCP read side in app/agents/reflection.py).
"""
from __future__ import annotations

import logging

from app.config import get_settings

log = logging.getLogger(__name__)

_provider = None


def init_tracing():
    """Register Phoenix tracing once. Returns the provider, or None if disabled."""
    global _provider
    if _provider is not None:
        return _provider

    settings = get_settings()
    # Gate on the API key (the example does the same): no key -> tracing off.
    if not settings.phoenix_api_key:
        return None
    try:
        # Lazy import: optional extras (pip install .[observability]).
        # register() reads PHOENIX_COLLECTOR_ENDPOINT + PHOENIX_API_KEY from env
        # and auto-attaches the auth header.
        from phoenix.otel import register

        _provider = register(
            project_name=settings.phoenix_project,
            batch=False,            # flush eagerly (short-lived runs)
            auto_instrument=True,   # hook the installed ADK instrumentor
            verbose=False,
        )
        log.info("Phoenix tracing enabled (project=%s)", settings.phoenix_project)
        return _provider
    except Exception as exc:  # noqa: BLE001 - tracing must never break the app
        log.warning("Phoenix tracing disabled: %s", exc)
        return None
