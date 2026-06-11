"""Conversation-derived workflow state.

The external contract remains conversation-first: Java sends free-form text.
Inside the agent core, each turn is interpreted into a proposed StateDelta, then
a deterministic reducer mutates this state. LLMs can propose transitions; code
owns the transition.
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class PhaseType(str, Enum):
    DATA_ANALYSIS = "DATA_ANALYSIS"
    HYPOTHESIS_GEN = "HYPOTHESIS_GEN"
    EXPERIMENT_PLAN = "EXPERIMENT_PLAN"
    EXPERIMENT_EVAL = "EXPERIMENT_EVAL"


class IntentType(str, Enum):
    INITIAL_RUN = "INITIAL_RUN"
    HYPOTHESIS_REQUEST = "HYPOTHESIS_REQUEST"
    PLAN_REQUEST = "PLAN_REQUEST"
    FREE_CHAT = "FREE_CHAT"
    BACKTRACK = "BACKTRACK"
    ARTIFACT_REVISION = "ARTIFACT_REVISION"
    ARTIFACT_QUERY = "ARTIFACT_QUERY"
    APPROVE = "APPROVE"


DEFAULT_WORKSPACE_ID = "demo_workspace"


class ScopeContext(BaseModel):
    """Runtime scope resolved for a turn.

    `workspace_id` is the tenant/data boundary. `campaign_id` is the no-login
    MVP working context, so every repository query carries both when available.
    """

    workspace_id: str = DEFAULT_WORKSPACE_ID
    campaign_id: str
    thread_id: str


class CompactLesson(BaseModel):
    phase: PhaseType
    summary: str = Field(
        ...,
        description="Compact lesson from prior failure/rejection; kept short for prompt hygiene.",
    )
    timestamp: float = Field(default_factory=time.time)


def _empty_phase_artifacts() -> dict[str, dict[str, Any]]:
    return {phase.value: {} for phase in PhaseType}


def _empty_phase_artifact_refs() -> dict[str, list[str]]:
    return {phase.value: [] for phase in PhaseType}


class SharedStateVector(BaseModel):
    """Mutable per-thread state for the macro graph and micro phase behavior."""

    scope: Optional[ScopeContext] = None
    user_query: str = ""
    current_phase: PhaseType = PhaseType.DATA_ANALYSIS
    target_phase: PhaseType = PhaseType.DATA_ANALYSIS
    user_intent: IntentType = IntentType.INITIAL_RUN

    compact_lessons: list[CompactLesson] = Field(default_factory=list)
    phase_artifacts: dict[str, dict[str, Any]] = Field(default_factory=_empty_phase_artifacts)
    phase_artifact_refs: dict[str, list[str]] = Field(default_factory=_empty_phase_artifact_refs)
    active_chat_history: list[dict[str, str]] = Field(default_factory=list)
    execution_plan: list[str] = Field(default_factory=list)
    revision: int = 0
    active_run_id: Optional[str] = None
    active_artifact_id: Optional[str] = None
    pending_approval_id: Optional[str] = None


class DeltaIntent(str, Enum):
    CHAT = "CHAT"
    START_ANALYSIS = "START_ANALYSIS"
    START_HYPOTHESIS = "START_HYPOTHESIS"
    START_PLAN = "START_PLAN"
    BACKTRACK = "BACKTRACK"
    ARTIFACT_REVISION = "ARTIFACT_REVISION"
    ARTIFACT_QUERY = "ARTIFACT_QUERY"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    CANCEL = "CANCEL"
    REQUEST_CLARIFICATION = "REQUEST_CLARIFICATION"


class ResponseMode(str, Enum):
    DIRECT = "DIRECT"
    DELEGATE = "DELEGATE"
    RERUN = "RERUN"
    CLARIFY = "CLARIFY"


class StateDeltaProposal(BaseModel):
    """Structured proposal extracted from free-form conversation."""

    intent: DeltaIntent
    response_mode: ResponseMode = ResponseMode.DIRECT
    target_phase: Optional[PhaseType] = None
    restart_from_phase: Optional[PhaseType] = None
    mutation: dict[str, Any] = Field(default_factory=dict)
    referenced_artifact_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    requires_confirmation: bool = False
    clarification_question: Optional[str] = None
    rationale: Optional[str] = None
    reply: Optional[str] = None

    @field_validator("target_phase", "restart_from_phase", mode="before")
    @classmethod
    def normalize_phase_aliases(cls, value: Any) -> Any:
        if value is None or isinstance(value, PhaseType):
            return value
        if not isinstance(value, str):
            return value
        normalized = value.strip().upper()
        aliases = {
            "ANALYSIS": PhaseType.DATA_ANALYSIS.value,
            "DATA": PhaseType.DATA_ANALYSIS.value,
            "SIGNAL_ANALYSIS": PhaseType.DATA_ANALYSIS.value,
            "HYPOTHESIS": PhaseType.HYPOTHESIS_GEN.value,
            "HYPOTHESIS_GENERATION": PhaseType.HYPOTHESIS_GEN.value,
            "HYPOTHESIS_GEN": PhaseType.HYPOTHESIS_GEN.value,
            "PLANNING": PhaseType.EXPERIMENT_PLAN.value,
            "PLAN": PhaseType.EXPERIMENT_PLAN.value,
            "PLAN_GENERATION": PhaseType.EXPERIMENT_PLAN.value,
            "EXPERIMENT_PLANNING": PhaseType.EXPERIMENT_PLAN.value,
            "EVALUATION": PhaseType.EXPERIMENT_EVAL.value,
            "EVAL": PhaseType.EXPERIMENT_EVAL.value,
            "EXPERIMENT_EVALUATION": PhaseType.EXPERIMENT_EVAL.value,
        }
        return aliases.get(normalized, normalized)


class ReducerDecisionType(str, Enum):
    ACCEPTED = "ACCEPTED"
    CLARIFY = "CLARIFY"
    REJECTED = "REJECTED"


class DelegationMode(str, Enum):
    DIRECT = "DIRECT"
    DELEGATE = "DELEGATE"
    RERUN = "RERUN"
    CLARIFY = "CLARIFY"


class ReducerDecision(BaseModel):
    decision: ReducerDecisionType
    delegation_mode: DelegationMode
    state: SharedStateVector
    reason: str
    delta: StateDeltaProposal
    revision_before: int
    revision_after: int


class DelegationDecision(BaseModel):
    mode: DelegationMode
    target_phase: PhaseType
    reason: str


def resolve_scope(
    thread_id: str,
    workspace_id: str | None,
    campaign_id: str | None,
    existing_state: SharedStateVector | None = None,
) -> ScopeContext | None:
    """Resolve turn scope from payload first, then persisted runtime state."""
    restored = existing_state.scope if existing_state else None
    resolved_campaign = campaign_id or (restored.campaign_id if restored else None)
    if not resolved_campaign:
        return None
    return ScopeContext(
        workspace_id=workspace_id or (restored.workspace_id if restored else DEFAULT_WORKSPACE_ID),
        campaign_id=resolved_campaign,
        thread_id=thread_id,
    )


def reduce_state(
    state: SharedStateVector,
    delta: StateDeltaProposal,
    user_query: str,
) -> ReducerDecision:
    """Apply a StateDelta with deterministic guards.

    The reducer is deliberately small and explicit. It is the only place where
    conversation-derived intent becomes authoritative workflow state.
    """
    before = state.revision
    state.user_query = user_query
    state.revision += 1
    state.active_chat_history.append({"role": "user", "content": user_query})

    from app.runtime.transitions import TRANSITION_GRAPH

    transition_result = TRANSITION_GRAPH.reduce(state, delta)
    return ReducerDecision(
        decision=transition_result.decision,
        delegation_mode=transition_result.delegation,
        state=state,
        reason=transition_result.render_reason(state, delta),
        delta=delta,
        revision_before=before,
        revision_after=state.revision,
    )


def decide_delegation(decision: ReducerDecision) -> DelegationDecision:
    return DelegationDecision(
        mode=decision.delegation_mode,
        target_phase=decision.state.target_phase,
        reason=decision.reason,
    )


def compact_state_summary(state: SharedStateVector) -> str:
    lessons = "; ".join(lesson.summary for lesson in state.compact_lessons[-3:])
    artifacts = {
        phase: sorted(value.keys()) for phase, value in state.phase_artifacts.items() if value
    }
    return (
        f"scope={state.scope.model_dump(mode='json') if state.scope else None}; "
        f"phase={state.current_phase.value}; target={state.target_phase.value}; "
        f"intent={state.user_intent.value}; revision={state.revision}; "
        f"artifact_keys={artifacts}; compact_lessons={lessons or 'none'}"
    )
