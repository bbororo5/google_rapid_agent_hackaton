"""ID + timestamp helpers. Prefixes match the contract patterns."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


def _new(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def signal_id() -> str:
    return _new("sig")


def hypothesis_id() -> str:
    return _new("hyp")


def experiment_id() -> str:
    return _new("exp")


def plan_id() -> str:
    return _new("plan")


def event_id() -> str:
    return _new("evt")


def observation_id() -> str:
    return _new("obs")


def step_id() -> str:
    return _new("step")


def trace_id() -> str:
    return _new("trc")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
