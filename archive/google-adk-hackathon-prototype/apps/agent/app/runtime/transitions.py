"""Declarative reducer transition graph.

LLMs propose a ProposedChange. This module owns the deterministic graph that
decides whether that proposal becomes a state transition, a clarification, or a
direct reply.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.runtime.state import (
    CompactLesson,
    DelegationMode,
    TurnIntent,
    UserIntent,
    PhaseType,
    ChangeDecisionType,
    ResponseMode,
    ConversationState,
    ProposedChange,
)

Reason = str | Callable[[ConversationState, ProposedChange], str]

_NEXT_PHASE = {
    PhaseType.DATA_ANALYSIS: PhaseType.HYPOTHESIS_GEN,
    PhaseType.HYPOTHESIS_GEN: PhaseType.EXPERIMENT_PLAN,
    PhaseType.EXPERIMENT_PLAN: PhaseType.EXPERIMENT_EVAL,
    PhaseType.EXPERIMENT_EVAL: PhaseType.EXPERIMENT_EVAL,
}


@dataclass(frozen=True, slots=True)
class TransitionTarget:
    phase: PhaseType | Callable[[ConversationState, ProposedChange], PhaseType]
    plan_from_target: bool = False

    def resolve(self, state: ConversationState, delta: ProposedChange) -> PhaseType:
        if callable(self.phase):
            return self.phase(state, delta)
        return self.phase

    def execution_plan(self, target: PhaseType) -> list[str]:
        if self.plan_from_target:
            return _plan_from(target)
        return [target.value]


@dataclass(frozen=True, slots=True)
class TransitionResult:
    decision: ChangeDecisionType
    delegation: DelegationMode
    reason: Reason
    target: TransitionTarget | None = None
    user_intent: UserIntent = UserIntent.FREE_CHAT
    current_phase_from_target: bool = True

    def apply(self, state: ConversationState, delta: ProposedChange) -> None:
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

    def render_reason(self, state: ConversationState, delta: ProposedChange) -> str:
        if callable(self.reason):
            return self.reason(state, delta)
        return self.reason


@dataclass(frozen=True, slots=True)
class GuardFailure:
    reason: Reason
    reply: str
    result: TransitionResult = TransitionResult(
        decision=ChangeDecisionType.ACCEPTED,
        delegation=DelegationMode.DIRECT,
        reason="guard failed",
        user_intent=UserIntent.FREE_CHAT,
    )


@dataclass(frozen=True, slots=True)
class Guard:
    name: str
    predicate: Callable[[ConversationState, ProposedChange], bool]
    failure: GuardFailure

    def evaluate(self, state: ConversationState, delta: ProposedChange) -> GuardFailure | None:
        if self.predicate(state, delta):
            return None
        return self.failure


@dataclass(frozen=True, slots=True)
class TransitionRule:
    intent: TurnIntent
    result: TransitionResult
    guards: tuple[Guard, ...] = ()
    effects: tuple[Callable[[ConversationState, ProposedChange], None], ...] = ()

    def apply(self, state: ConversationState, delta: ProposedChange) -> TransitionResult:
        # 1) 가드(전제조건)를 먼저 통과해야 한다. 하나라도 실패하면 그 자리에서
        #    "직접 답변(안내문)"으로 돌리고 끝낸다 (예: 신호 없이 가설 요청).
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
        # 2) 모든 가드 통과 -> 정상 전이를 상태에 반영하고, 부수 효과(effects)를 실행한다.
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

    def reduce(self, state: ConversationState, delta: ProposedChange) -> TransitionResult:
        if delta.confidence < 0.55 or delta.requires_confirmation:
            self._clarify_result.apply(state, delta)
            return self._clarify_result
        if delta.intent == TurnIntent.APPROVE and not state.pending_approval_id:
            APPROVE_AS_CONTINUE.apply(state, delta)
            return APPROVE_AS_CONTINUE
        rule = self._rules.get(delta.intent)
        if rule:
            return rule.apply(state, delta)
        self._default_result.apply(state, delta)
        return self._default_result


def _current_phase(state: ConversationState, _delta: ProposedChange) -> PhaseType:
    return state.current_phase


def _backtrack_target(_state: ConversationState, delta: ProposedChange) -> PhaseType:
    return delta.target_phase or delta.restart_from_phase or PhaseType.DATA_ANALYSIS


def _artifact_revision_target(state: ConversationState, delta: ProposedChange) -> PhaseType:
    return delta.target_phase or state.current_phase


def _approval_target(state: ConversationState, _delta: ProposedChange) -> PhaseType:
    return _NEXT_PHASE[state.current_phase]


def _has_analysis_input(state: ConversationState, delta: ProposedChange) -> bool:
    return bool(
        delta.mutation.get("has_csv_attachment")
        or state.phase_artifacts[PhaseType.DATA_ANALYSIS.value].get("signals")
    )


def _has_signals(state: ConversationState, _delta: ProposedChange) -> bool:
    return bool(state.phase_artifacts[PhaseType.DATA_ANALYSIS.value].get("signals"))


def _has_hypotheses(state: ConversationState, _delta: ProposedChange) -> bool:
    return bool(state.phase_artifacts[PhaseType.HYPOTHESIS_GEN.value].get("hypotheses"))


def _backtrack_effect(state: ConversationState, delta: ProposedChange) -> None:
    target = _backtrack_target(state, delta)
    _record_lesson(state, target, delta)
    _invalidate_downstream_artifacts(state, target)


def _backtrack_reason(state: ConversationState, delta: ProposedChange) -> str:
    return f"backtrack accepted to {_backtrack_target(state, delta).value}"


def _plan_from(start: PhaseType) -> list[str]:
    phases = list(PhaseType)
    idx = phases.index(start)
    return [phase.value for phase in phases[idx:]]


def _record_lesson(state: ConversationState, phase: PhaseType, delta: ProposedChange) -> None:
    if not delta.mutation:
        return
    parts = [f"{key}={value}" for key, value in sorted(delta.mutation.items())]
    summary = f"Backtrack requested for {phase.value}; changed " + ", ".join(parts[:4])
    state.compact_lessons.append(CompactLesson(phase=phase, summary=summary[:280]))
    state.compact_lessons = state.compact_lessons[-6:]


def _invalidate_downstream_artifacts(state: ConversationState, target: PhaseType) -> None:
    phases = list(PhaseType)
    start = phases.index(target)
    for phase in phases[start:]:
        state.phase_artifacts[phase.value] = {}
        state.phase_artifact_refs[phase.value] = []


DIRECT_FREE_CHAT = TransitionResult(
    decision=ChangeDecisionType.ACCEPTED,
    delegation=DelegationMode.DIRECT,
    reason="direct orchestrator reply",
    user_intent=UserIntent.FREE_CHAT,
)

APPROVE_AS_CONTINUE = TransitionResult(
    decision=ChangeDecisionType.ACCEPTED,
    delegation=DelegationMode.RERUN,
    reason="approval-like continuation without pending approval should run the next phase",
    target=TransitionTarget(_approval_target, plan_from_target=True),
    user_intent=UserIntent.APPROVE,
)

TRANSITION_GRAPH = TransitionGraph(
    clarify_result=TransitionResult(
        decision=ChangeDecisionType.CLARIFY,
        delegation=DelegationMode.CLARIFY,
        reason="low confidence or confirmation required",
        user_intent=UserIntent.FREE_CHAT,
    ),
    default_result=DIRECT_FREE_CHAT,
    rules=(
        TransitionRule(
            intent=TurnIntent.BACKTRACK,
            result=TransitionResult(
                decision=ChangeDecisionType.ACCEPTED,
                delegation=DelegationMode.RERUN,
                reason=_backtrack_reason,
                target=TransitionTarget(_backtrack_target),
                user_intent=UserIntent.BACKTRACK,
            ),
            effects=(_backtrack_effect,),
        ),
        TransitionRule(
            intent=TurnIntent.START_ANALYSIS,
            result=TransitionResult(
                decision=ChangeDecisionType.ACCEPTED,
                delegation=DelegationMode.RERUN,
                reason="analysis run requested",
                target=TransitionTarget(PhaseType.DATA_ANALYSIS),
                user_intent=UserIntent.INITIAL_RUN,
            ),
            guards=(
                Guard(
                    name="analysis_input_available",
                    predicate=_has_analysis_input,
                    failure=GuardFailure(
                        reason="analysis request blocked until csv attachment or prior analysis exists",
                        reply="Attach a campaign metrics CSV to start analysis. For now, I can help clarify which metric or window to inspect first.",
                    ),
                ),
            ),
        ),
        TransitionRule(
            intent=TurnIntent.START_HYPOTHESIS,
            result=TransitionResult(
                decision=ChangeDecisionType.ACCEPTED,
                delegation=DelegationMode.RERUN,
                reason="hypothesis generation requested",
                target=TransitionTarget(PhaseType.HYPOTHESIS_GEN),
                user_intent=UserIntent.HYPOTHESIS_REQUEST,
            ),
            guards=(
                Guard(
                    name="signals_available",
                    predicate=_has_signals,
                    failure=GuardFailure(
                        reason="hypothesis request blocked until analysis artifact exists",
                        reply="There is no analysis result yet, so I did not generate hypotheses. Analyze campaign metrics first, then I can build hypotheses from those signals.",
                    ),
                ),
            ),
        ),
        TransitionRule(
            intent=TurnIntent.START_PLAN,
            result=TransitionResult(
                decision=ChangeDecisionType.ACCEPTED,
                delegation=DelegationMode.RERUN,
                reason="experiment planning requested",
                target=TransitionTarget(PhaseType.EXPERIMENT_PLAN),
                user_intent=UserIntent.PLAN_REQUEST,
            ),
            guards=(
                Guard(
                    name="hypotheses_available",
                    predicate=_has_hypotheses,
                    failure=GuardFailure(
                        reason="plan request blocked until hypothesis artifact exists",
                        reply="There is no confirmed hypothesis yet, so I did not draft an experiment plan. Generate hypotheses from the analysis signals first, then continue to planning.",
                    ),
                ),
            ),
        ),
        TransitionRule(
            intent=TurnIntent.ARTIFACT_REVISION,
            result=TransitionResult(
                decision=ChangeDecisionType.ACCEPTED,
                delegation=DelegationMode.DELEGATE,
                reason="phase-local artifact revision should be delegated",
                target=TransitionTarget(_artifact_revision_target),
                user_intent=UserIntent.ARTIFACT_REVISION,
                current_phase_from_target=False,
            ),
        ),
        TransitionRule(
            intent=TurnIntent.ARTIFACT_QUERY,
            result=TransitionResult(
                decision=ChangeDecisionType.ACCEPTED,
                delegation=DelegationMode.DIRECT,
                reason="artifact query answered from runtime state",
                target=TransitionTarget(_current_phase),
                user_intent=UserIntent.ARTIFACT_QUERY,
                current_phase_from_target=False,
            ),
        ),
        TransitionRule(
            intent=TurnIntent.APPROVE,
            result=TransitionResult(
                decision=ChangeDecisionType.ACCEPTED,
                delegation=DelegationMode.DIRECT,
                reason="approval intent detected; business persistence remains Java-owned",
                target=TransitionTarget(_approval_target, plan_from_target=True),
                user_intent=UserIntent.APPROVE,
            ),
        ),
    ),
)
