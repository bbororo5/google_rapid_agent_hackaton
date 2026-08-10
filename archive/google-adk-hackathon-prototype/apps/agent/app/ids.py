"""ID + timestamp helpers.

Prefixes match the contract regex patterns (e.g. ^sig_[A-Za-z0-9_]+$). Java owns
run_/brief_/req_ ids; Python mints the ones it produces (signals, hypotheses,
experiments, plans, events, observations, steps, traces).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


def _new(prefix: str) -> str:
    # Short random suffix; collision risk is negligible for a demo/run lifetime.
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def signal_id() -> str:
    return _new("sig")


def hypothesis_id() -> str:
    return _new("hyp")


def experiment_id() -> str:
    return _new("exp")


def plan_id() -> str:
    return _new("plan")


def message_id() -> str:
    return _new("msg")


def approval_id() -> str:
    return _new("appr")


def event_id() -> str:
    return _new("evt")


def observation_id() -> str:
    return _new("obs")


def step_id() -> str:
    return _new("step")


def trace_id() -> str:
    return _new("trc")


def now_iso() -> str:
    # Timezone-aware UTC ISO-8601, matching the contract's date-time format.
    return datetime.now(timezone.utc).isoformat()
