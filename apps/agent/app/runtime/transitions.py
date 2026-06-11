"""Declarative reducer transition graph.

LLMs propose a StateDeltaProposal. This module owns the deterministic graph that
decides whether that proposal becomes a state transition, a clarification, or a
direct reply.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.runtime.state import (
    CompactLesson,
    DelegationMode,
    DeltaIntent,
    IntentType,
    PhaseType,
    ReducerDecisionType,
    ResponseMode,
    SharedStateVector,
    StateDeltaProposal,
)

Reason = str | Callable[[SharedStateVector, StateDeltaProposal], str]

_NEXT_PHASE = {
    PhaseType.DATA_ANALYSIS: PhaseType.HYPOTHESIS_GEN,
    PhaseType.HYPOTHESIS_GEN: PhaseType.EXPERIMENT_PLAN,
    PhaseType.EXPERIMENT_PLAN: PhaseType.EXPERIMENT_EVAL,
    PhaseType.EXPERIMENT_EVAL: PhaseType.EXPERIMENT_EVAL,
}


@dataclass(frozen=True, slots=True)
class TransitionTarget:
    phase: PhaseType | Callable[[SharedStateVector, StateDeltaProposal], PhaseType]
    plan_from_target: bool = False

    def resolve(self, state: SharedStateVector, delta: StateDeltaProposal) -> PhaseType:
        if callable(self.phase):
            return self.phase(state, delta)
        return self.phase

    def execution_plan(self, target: PhaseType) -> list[str]:
        if self.plan_from_target:
            return _plan_from(target)
        return [target.value]


@dataclass(frozen=True, slots=True)
class TransitionResult:
    decision: ReducerDecisionType
    delegation: DelegationMode
    reason: Reason
    target: TransitionTarget | None = None
    user_intent: IntentType = IntentType.FREE_CHAT
    current_phase_from_target: bool = True

    def apply(self, state: SharedStateVector, delta: StateDeltaProposal) -> None:
        if self.target is not None:
            target = self.target.resolve(state, delta)
            state.target_phase = target
            if self.current_phase_from_target:
                state.current_phase = target
            state.execution_plan = self.target.execution_plan(target)
        else:
            state.target_phase = state.current_phase
            state.execution_plan = [state.current_phase.value]
        state.user_intent = self.user_intent

    def render_reason(self, state: SharedStateVector, delta: StateDeltaProposal) -> str:
        if callable(self.reason):
            return self.reason(state, delta)
        return self.reason


@dataclass(frozen=True, slots=True)
class GuardFailure:
    reason: Reason
    reply: str
    result: TransitionResult = TransitionResult(
        decision=ReducerDecisionType.ACCEPTED,
        delegation=DelegationMode.DIRECT,
        reason="guard failed",
        user_intent=IntentType.FREE_CHAT,
    )


@dataclass(frozen=True, slots=True)
class Guard:
    name: str
    predicate: Callable[[SharedStateVector, StateDeltaProposal], bool]
    failure: GuardFailure

    def evaluate(self, state: SharedStateVector, delta: StateDeltaProposal) -> GuardFailure | None:
        if self.predicate(state, delta):
            return None
        return self.failure


@dataclass(frozen=True, slots=True)
class TransitionRule:
    intent: DeltaIntent
    result: TransitionResult
    guards: tuple[Guard, ...] = ()
    effects: tuple[Callable[[SharedStateVector, StateDeltaProposal], None], ...] = ()

    def apply(self, state: SharedStateVector, delta: StateDeltaProposal) -> TransitionResult:
        for guard in self.guards:
            failure = guard.evaluate(state, delta)
            if failure:
                delta.response_mode = ResponseMode.DIRECT
                delta.reply = delta.reply or failure.reply
                failure_result = TransitionResult(
                    decision=failure.result.decision,
                    delegation=failure.result.delegation,
                    reason=failure.reason,
                    target=failure.result.target,
                    user_intent=failure.result.user_intent,
                    current_phase_from_target=failure.result.current_phase_from_target,
                )
                failure_result.apply(state, delta)
                return failure_result
        self.result.apply(state, delta)
        for effect in self.effects:
            effect(state, delta)
        return self.result


class TransitionGraph:
    def __init__(
        self,
        rules: tuple[TransitionRule, ...],
        clarify_result: TransitionResult,
        default_result: TransitionResult,
    ) -> None:
        self._rules = {rule.intent: rule for rule in rules}
        self._clarify_result = clarify_result
        self._default_result = default_result

    def reduce(self, state: SharedStateVector, delta: StateDeltaProposal) -> TransitionResult:
        if delta.confidence < 0.55 or delta.requires_confirmation:
            self._clarify_result.apply(state, delta)
            return self._clarify_result
        rule = self._rules.get(delta.intent)
        if rule:
            return rule.apply(state, delta)
        self._default_result.apply(state, delta)
        return self._default_result


def _current_phase(state: SharedStateVector, _delta: StateDeltaProposal) -> PhaseType:
    return state.current_phase


def _backtrack_target(_state: SharedStateVector, delta: StateDeltaProposal) -> PhaseType:
    return delta.target_phase or delta.restart_from_phase or PhaseType.DATA_ANALYSIS


def _artifact_revision_target(state: SharedStateVector, delta: StateDeltaProposal) -> PhaseType:
    return delta.target_phase or state.current_phase


def _approval_target(state: SharedStateVector, _delta: StateDeltaProposal) -> PhaseType:
    return _NEXT_PHASE[state.current_phase]


def _has_analysis_input(state: SharedStateVector, delta: StateDeltaProposal) -> bool:
    return bool(
        delta.mutation.get("has_csv_attachment")
        or state.phase_artifacts[PhaseType.DATA_ANALYSIS.value].get("signals")
    )


def _has_signals(state: SharedStateVector, _delta: StateDeltaProposal) -> bool:
    return bool(state.phase_artifacts[PhaseType.DATA_ANALYSIS.value].get("signals"))


def _has_hypotheses(state: SharedStateVector, _delta: StateDeltaProposal) -> bool:
    return bool(state.phase_artifacts[PhaseType.HYPOTHESIS_GEN.value].get("hypotheses"))


def _backtrack_effect(state: SharedStateVector, delta: StateDeltaProposal) -> None:
    target = _backtrack_target(state, delta)
    _record_lesson(state, target, delta)
    _invalidate_downstream_artifacts(state, target)


def _backtrack_reason(state: SharedStateVector, delta: StateDeltaProposal) -> str:
    return f"backtrack accepted to {_backtrack_target(state, delta).value}"


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


DIRECT_FREE_CHAT = TransitionResult(
    decision=ReducerDecisionType.ACCEPTED,
    delegation=DelegationMode.DIRECT,
    reason="direct orchestrator reply",
    user_intent=IntentType.FREE_CHAT,
)

TRANSITION_GRAPH = TransitionGraph(
    clarify_result=TransitionResult(
        decision=ReducerDecisionType.CLARIFY,
        delegation=DelegationMode.CLARIFY,
        reason="low confidence or confirmation required",
        user_intent=IntentType.FREE_CHAT,
    ),
    default_result=DIRECT_FREE_CHAT,
    rules=(
        TransitionRule(
            intent=DeltaIntent.BACKTRACK,
            result=TransitionResult(
                decision=ReducerDecisionType.ACCEPTED,
                delegation=DelegationMode.RERUN,
                reason=_backtrack_reason,
                target=TransitionTarget(_backtrack_target),
                user_intent=IntentType.BACKTRACK,
            ),
            effects=(_backtrack_effect,),
        ),
        TransitionRule(
            intent=DeltaIntent.START_ANALYSIS,
            result=TransitionResult(
                decision=ReducerDecisionType.ACCEPTED,
                delegation=DelegationMode.RERUN,
                reason="analysis run requested",
                target=TransitionTarget(PhaseType.DATA_ANALYSIS),
                user_intent=IntentType.INITIAL_RUN,
            ),
            guards=(
                Guard(
                    name="analysis_input_available",
                    predicate=_has_analysis_input,
                    failure=GuardFailure(
                        reason="analysis request blocked until csv attachment or prior analysis exists",
                        reply="캠페인 지표 CSV를 첨부하면 바로 분석을 시작할 수 있습니다. 지금은 어떤 기준으로 볼지 먼저 같이 정리해볼게요.",
                    ),
                ),
            ),
        ),
        TransitionRule(
            intent=DeltaIntent.START_HYPOTHESIS,
            result=TransitionResult(
                decision=ReducerDecisionType.ACCEPTED,
                delegation=DelegationMode.RERUN,
                reason="hypothesis generation requested",
                target=TransitionTarget(PhaseType.HYPOTHESIS_GEN),
                user_intent=IntentType.HYPOTHESIS_REQUEST,
            ),
            guards=(
                Guard(
                    name="signals_available",
                    predicate=_has_signals,
                    failure=GuardFailure(
                        reason="hypothesis request blocked until analysis artifact exists",
                        reply="분석 결과가 아직 없어서 가설을 바로 세우지는 않았습니다. 먼저 캠페인 지표를 분석한 뒤, 그 신호를 바탕으로 가설을 만들 수 있어요.",
                    ),
                ),
            ),
        ),
        TransitionRule(
            intent=DeltaIntent.START_PLAN,
            result=TransitionResult(
                decision=ReducerDecisionType.ACCEPTED,
                delegation=DelegationMode.RERUN,
                reason="experiment planning requested",
                target=TransitionTarget(PhaseType.EXPERIMENT_PLAN),
                user_intent=IntentType.PLAN_REQUEST,
            ),
            guards=(
                Guard(
                    name="hypotheses_available",
                    predicate=_has_hypotheses,
                    failure=GuardFailure(
                        reason="plan request blocked until hypothesis artifact exists",
                        reply="확정된 가설이 아직 없어서 실험 계획을 바로 만들지는 않았습니다. 먼저 분석 신호를 보고 가설을 세운 뒤 계획으로 이어가겠습니다.",
                    ),
                ),
            ),
        ),
        TransitionRule(
            intent=DeltaIntent.ARTIFACT_REVISION,
            result=TransitionResult(
                decision=ReducerDecisionType.ACCEPTED,
                delegation=DelegationMode.DELEGATE,
                reason="phase-local artifact revision should be delegated",
                target=TransitionTarget(_artifact_revision_target),
                user_intent=IntentType.ARTIFACT_REVISION,
                current_phase_from_target=False,
            ),
        ),
        TransitionRule(
            intent=DeltaIntent.ARTIFACT_QUERY,
            result=TransitionResult(
                decision=ReducerDecisionType.ACCEPTED,
                delegation=DelegationMode.DIRECT,
                reason="artifact query answered from runtime state",
                target=TransitionTarget(_current_phase),
                user_intent=IntentType.ARTIFACT_QUERY,
                current_phase_from_target=False,
            ),
        ),
        TransitionRule(
            intent=DeltaIntent.APPROVE,
            result=TransitionResult(
                decision=ReducerDecisionType.ACCEPTED,
                delegation=DelegationMode.DIRECT,
                reason="approval intent detected; business persistence remains Java-owned",
                target=TransitionTarget(_approval_target, plan_from_target=True),
                user_intent=IntentType.APPROVE,
            ),
        ),
    ),
)
