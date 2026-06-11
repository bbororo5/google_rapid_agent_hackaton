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

from pydantic import BaseModel, Field


class PhaseType(str, Enum):
    DATA_ANALYSIS = "DATA_ANALYSIS"
    HYPOTHESIS_GEN = "HYPOTHESIS_GEN"
    EXPERIMENT_PLAN = "EXPERIMENT_PLAN"
    EXPERIMENT_EVAL = "EXPERIMENT_EVAL"


class IntentType(str, Enum):
    INITIAL_RUN = "INITIAL_RUN"
    FREE_CHAT = "FREE_CHAT"
    BACKTRACK = "BACKTRACK"
    ARTIFACT_REVISION = "ARTIFACT_REVISION"
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
    BACKTRACK = "BACKTRACK"
    ARTIFACT_REVISION = "ARTIFACT_REVISION"
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


_NEXT_PHASE = {
    PhaseType.DATA_ANALYSIS: PhaseType.HYPOTHESIS_GEN,
    PhaseType.HYPOTHESIS_GEN: PhaseType.EXPERIMENT_PLAN,
    PhaseType.EXPERIMENT_PLAN: PhaseType.EXPERIMENT_EVAL,
    PhaseType.EXPERIMENT_EVAL: PhaseType.EXPERIMENT_EVAL,
}


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
    if len(state.active_chat_history) > 12:
        state.active_chat_history = state.active_chat_history[-12:]

    if delta.confidence < 0.55 or delta.requires_confirmation:
        state.user_intent = IntentType.FREE_CHAT
        state.execution_plan = [state.current_phase.value]
        return ReducerDecision(
            decision=ReducerDecisionType.CLARIFY,
            delegation_mode=DelegationMode.CLARIFY,
            state=state,
            reason="low confidence or confirmation required",
            delta=delta,
            revision_before=before,
            revision_after=state.revision,
        )

    if delta.intent == DeltaIntent.BACKTRACK:
        target = delta.target_phase or delta.restart_from_phase or PhaseType.DATA_ANALYSIS
        state.target_phase = target
        state.current_phase = target
        state.user_intent = IntentType.BACKTRACK
        state.execution_plan = _plan_from(target)
        _record_lesson(state, target, delta)
        _invalidate_downstream_artifacts(state, target)
        return ReducerDecision(
            decision=ReducerDecisionType.ACCEPTED,
            delegation_mode=DelegationMode.RERUN,
            state=state,
            reason=f"backtrack accepted to {target.value}",
            delta=delta,
            revision_before=before,
            revision_after=state.revision,
        )

    if delta.intent == DeltaIntent.START_ANALYSIS:
        state.target_phase = PhaseType.DATA_ANALYSIS
        state.current_phase = PhaseType.DATA_ANALYSIS
        state.user_intent = IntentType.INITIAL_RUN
        state.execution_plan = _plan_from(PhaseType.DATA_ANALYSIS)
        return ReducerDecision(
            decision=ReducerDecisionType.ACCEPTED,
            delegation_mode=DelegationMode.RERUN,
            state=state,
            reason="analysis run requested",
            delta=delta,
            revision_before=before,
            revision_after=state.revision,
        )

    if delta.intent == DeltaIntent.ARTIFACT_REVISION:
        state.user_intent = IntentType.ARTIFACT_REVISION
        state.target_phase = delta.target_phase or state.current_phase
        state.execution_plan = [state.target_phase.value]
        return ReducerDecision(
            decision=ReducerDecisionType.ACCEPTED,
            delegation_mode=DelegationMode.DELEGATE,
            state=state,
            reason="phase-local artifact revision should be delegated",
            delta=delta,
            revision_before=before,
            revision_after=state.revision,
        )

    if delta.intent == DeltaIntent.APPROVE:
        state.user_intent = IntentType.APPROVE
        state.current_phase = _NEXT_PHASE[state.current_phase]
        state.target_phase = state.current_phase
        state.execution_plan = _plan_from(state.current_phase)
        return ReducerDecision(
            decision=ReducerDecisionType.ACCEPTED,
            delegation_mode=DelegationMode.DIRECT,
            state=state,
            reason="approval intent detected; business persistence remains Java-owned",
            delta=delta,
            revision_before=before,
            revision_after=state.revision,
        )

    state.user_intent = IntentType.FREE_CHAT
    state.target_phase = state.current_phase
    state.execution_plan = [state.current_phase.value]
    return ReducerDecision(
        decision=ReducerDecisionType.ACCEPTED,
        delegation_mode=DelegationMode.DIRECT,
        state=state,
        reason="direct orchestrator reply",
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


def _plan_from(start: PhaseType) -> list[str]:
    phases = list(PhaseType)
    idx = phases.index(start)
    return [phase.value for phase in phases[idx:]]


def _record_lesson(state: SharedStateVector, phase: PhaseType, delta: StateDeltaProposal) -> None:
    if not delta.mutation:
        return
    parts = [f"{key}={value}" for key, value in sorted(delta.mutation.items())]
    summary = f"Backtrack requested for {phase.value}; changed " + ", ".join(parts[:4])
    state.compact_lessons.append(CompactLesson(phase=phase, summary=summary[:280]))
    state.compact_lessons = state.compact_lessons[-6:]


def _invalidate_downstream_artifacts(state: SharedStateVector, target: PhaseType) -> None:
    phases = list(PhaseType)
    start = phases.index(target)
    for phase in phases[start:]:
        state.phase_artifacts[phase.value] = {}
        state.phase_artifact_refs[phase.value] = []
