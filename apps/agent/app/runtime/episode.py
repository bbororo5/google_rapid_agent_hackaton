"""Episodic memory model (ADR-005, Phase 2).

An episode is one semantic unit of the conversation: the dialogue span since the
last checkpoint, plus a state snapshot that makes the episode a restore point.
Episodes are append-only and durable in Elastic (`agent_episodes`); the live
working state lives in Redis (hot tier).

MVP: `summary` and `embedding` are deferred (ADR-005 C6). We persist the raw
span and the state snapshot only, and retrieve with hard filter + recency.
"""
from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.runtime.state import PhaseType, ConversationState


class EpisodeOutcome(str, Enum):
    FORWARD = "forward"      # phase boundary: a round completed and advanced
    APPROVE = "approve"
    REJECT = "reject"
    BACKTRACK = "backtrack"  # discarded/rewound work (failures are kept on purpose)


class StateSnapshot(BaseModel):
    """The restore point. lessons are lossy, so state is snapshotted (Risk 3)."""

    current_phase: PhaseType
    target_phase: PhaseType
    phase_artifact_refs: dict[str, list[str]] = Field(default_factory=dict)
    key_params: dict[str, Any] = Field(default_factory=dict)
    revision: int


class Episode(BaseModel):
    episode_id: str = Field(default_factory=lambda: f"ep_{uuid.uuid4().hex[:12]}")
    workspace_id: str
    campaign_id: str
    thread_id: str
    phase: PhaseType
    outcome: EpisodeOutcome
    run_id: str | None = None
    raw: list[dict[str, str]] = Field(default_factory=list)
    summary: str | None = None          # MVP: None (LLM summary deferred)
    embedding: list[float] | None = None  # MVP: None (embedding deferred)
    state_snapshot: StateSnapshot
    created_at: float = Field(default_factory=time.time)


def build_episode(
    state: ConversationState,
    outcome: EpisodeOutcome,
    raw_buffer: list[dict[str, str]],
    key_params: dict[str, Any] | None = None,
) -> Episode:
    """Build an episode from the live state and the dialogue buffer.

    Requires a resolved scope; callers must guard on `state.scope` first.
    """
    scope = state.scope
    if scope is None:  # defensive: episodes are always scoped (C5)
        raise ValueError("cannot build an episode without a resolved scope")
    return Episode(
        workspace_id=scope.workspace_id,
        campaign_id=scope.campaign_id,
        thread_id=scope.thread_id,
        phase=state.current_phase,
        outcome=outcome,
        run_id=state.active_run_id,
        raw=[dict(entry) for entry in raw_buffer],
        state_snapshot=StateSnapshot(
            current_phase=state.current_phase,
            target_phase=state.target_phase,
            phase_artifact_refs={k: list(v) for k, v in state.phase_artifact_refs.items()},
            key_params=dict(key_params or {}),
            revision=state.revision,
        ),
    )
