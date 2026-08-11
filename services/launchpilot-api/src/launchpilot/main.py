"""Stable ASGI entrypoint; application composition lives in bootstrap."""

from launchpilot.bootstrap.app import app

__all__ = ["app"]
