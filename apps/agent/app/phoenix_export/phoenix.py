"""Phoenix/OpenInference tracing for evaluation and agent trace inspection."""

from __future__ import annotations

import logging

log = logging.getLogger("launchpilot.phoenix_export")

_provider = None


def init_phoenix_export():
    """Register Phoenix tracing once. Returns the provider, or None if disabled."""
    global _provider
    if _provider is not None:
        return _provider

    from app.config import get_settings

    settings = get_settings()
    if not settings.phoenix_api_key:
        return None

    try:
        from phoenix.otel import register

        kwargs = dict(
            project_name=settings.phoenix_project,
            batch=False,
            auto_instrument=True,
            verbose=False,
        )
        endpoint = None
        if settings.phoenix_endpoint:
            base = settings.phoenix_endpoint.rstrip("/")
            endpoint = base if base.endswith("/v1/traces") else f"{base}/v1/traces"
            kwargs["endpoint"] = endpoint
            kwargs["protocol"] = "http/protobuf"

        _provider = register(**kwargs)
        log.info(
            "Phoenix tracing enabled (project=%s endpoint=%s)",
            settings.phoenix_project,
            endpoint or "<env-default>",
        )
        return _provider
    except Exception as exc:  # noqa: BLE001 - tracing must never break the app
        log.warning("Phoenix tracing disabled: %s", exc)
        return None
