"""Declarative reducer transition graph.

LLMs propose a ProposedChange. This module owns the deterministic graph that
decides whether that proposal becomes a state transition, a clarification, or a
direct reply.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.contracts import Confidence, Hypothesis
from app.ids import hypothesis_id
from app.runtime.state import (
    CompactLesson,
    DelegationMode,
    TurnIntent,
    UserIntent,
    PhaseType,
    ChangeDecisionType,
    PendingProposal,
    ResponseMode,
    ConversationState,
    ProposedChange,
    SkipSubtype,
    is_gate_still_valid,
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

        # 대기중인 제안(pending_gate)이 있으면, 이 응답이 "그 제안 하나"에 대한
        # 긍정 답변인지만 좁게 확인한다. 통과하면 확정, 아니면(불일치든 만료든)
        # 조용히 지우고 정상 분류로 넘어간다 — 재촉/누적 없이 한 번만 묻는다.
        if state.pending_gate is not None:
            gate = state.pending_gate
            if is_gate_still_valid(gate, state.revision) and _affirmative_reply(state.user_query):
                return _confirm_pending_gate(state, delta)
            state.pending_gate = None

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


def _skip_target(_state: ConversationState, delta: ProposedChange) -> PhaseType:
    assert delta.target_phase is not None  # guarded by _skip_target_valid before this runs
    return delta.target_phase


def _has_pending_approval(state: ConversationState, _delta: ProposedChange) -> bool:
    return state.pending_approval_id is not None


_AFFIRMATIVE_MARKERS = (
    "yes", "yeah", "yep", "sure", "ok", "okay", "sounds good", "go ahead",
    "let's do it", "please do", "do it",
    "네", "넵", "좋아요", "좋아", "해주세요", "해줘", "진행", "그렇게",
)


def _affirmative_reply(text: str) -> bool:
    # 의도적으로 좁은 키워드 매칭이다 — 애매한 문장을 승인으로 오인하지 않도록,
    # 이 순간만큼은 넓은 자연어 이해보다 예측 가능한 규칙을 우선한다.
    lowered = text.strip().lower()
    if not lowered:
        return False
    return any(marker in lowered for marker in _AFFIRMATIVE_MARKERS)


def _confirm_pending_gate(state: ConversationState, delta: ProposedChange) -> TransitionResult:
    gate = state.pending_gate
    assert gate is not None
    state.pending_gate = None
    target = gate.target_phase
    result = TransitionResult(
        decision=ChangeDecisionType.ACCEPTED,
        delegation=DelegationMode.RERUN,
        reason=f"pending proposal confirmed -> {target.value}",
        target=TransitionTarget(target, plan_from_target=True),
        user_intent=(
            UserIntent.HYPOTHESIS_REQUEST
            if target == PhaseType.HYPOTHESIS_GEN
            else UserIntent.PLAN_REQUEST
        ),
    )
    result.apply(state, delta)
    return result


def _has_analysis_input(state: ConversationState, delta: ProposedChange) -> bool:
    return bool(
        delta.mutation.get("has_csv_attachment")
        or state.phase_artifacts[PhaseType.DATA_ANALYSIS.value].get("signals")
    )


def _has_signals(state: ConversationState, _delta: ProposedChange) -> bool:
    return bool(state.phase_artifacts[PhaseType.DATA_ANALYSIS.value].get("signals"))


def _has_hypotheses(state: ConversationState, _delta: ProposedChange) -> bool:
    return bool(state.phase_artifacts[PhaseType.HYPOTHESIS_GEN.value].get("hypotheses"))


def _skip_target_valid(_state: ConversationState, delta: ProposedChange) -> bool:
    return delta.target_phase in (PhaseType.HYPOTHESIS_GEN, PhaseType.EXPERIMENT_PLAN)


def _skip_payload_present(_state: ConversationState, delta: ProposedChange) -> bool:
    if delta.skip_subtype in (SkipSubtype.FULL_ARTIFACT, SkipSubtype.PARTIAL_INPUT):
        return bool(delta.skip_payload and delta.skip_payload.strip())
    return True


def _materialize_skip(state: ConversationState, delta: ProposedChange) -> None:
    """제안-확인 없이 사용자가 직접 던진 산출물/힌트를 반영한다.

    FULL_ARTIFACT: 이미 확보된 신호에 근거를 걸어 가설 산출물로 바로 채택한다
    (전략가 재호출 없이 EXPERIMENT_PLAN으로 직행할 수 있게 된다).
    PARTIAL_INPUT: 힌트만 누적 맥락(hypothesis_context)에 남기고, 전략가는
    그대로 호출되어 이 힌트를 참고자료로 쓴다.
    REUSE_PRIOR: 아무것도 새로 만들지 않는다 — 기존 가드(_has_signals 등)가
    이미 저장된 산출물을 그대로 인정한다.
    """
    if delta.skip_subtype == SkipSubtype.FULL_ARTIFACT:
        signals = state.phase_artifacts[PhaseType.DATA_ANALYSIS.value].get("signals", [])
        signal_ids = [s["id"] for s in signals]
        hyp = Hypothesis(
            id=hypothesis_id(),
            signal_ids=signal_ids,
            statement=delta.skip_payload or "",
            rationale="Supplied directly by the user (skip).",
            confidence=Confidence.medium,
            supporting_evidence_refs=[],
            caveats=["User-supplied hypothesis; not independently derived by the strategist agent."],
        )
        state.phase_artifacts[PhaseType.HYPOTHESIS_GEN.value]["hypotheses"] = [
            hyp.model_dump(mode="json")
        ]
    elif delta.skip_subtype == SkipSubtype.PARTIAL_INPUT:
        state.hypothesis_context.user_hunch = delta.skip_payload


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
            intent=TurnIntent.SKIP_SUBMIT,
            result=TransitionResult(
                decision=ChangeDecisionType.ACCEPTED,
                delegation=DelegationMode.RERUN,
                reason="user-supplied artifact/hint accepted as a skip",
                target=TransitionTarget(_skip_target, plan_from_target=True),
                user_intent=UserIntent.SKIP_SUBMIT,
            ),
            guards=(
                Guard(
                    name="skip_target_valid",
                    predicate=_skip_target_valid,
                    failure=GuardFailure(
                        reason="skip target must be hypothesis_gen or experiment_plan",
                        reply="I can only skip ahead to hypothesis generation or experiment planning. Which one did you mean?",
                    ),
                ),
                Guard(
                    name="skip_payload_present",
                    predicate=_skip_payload_present,
                    failure=GuardFailure(
                        reason="skip blocked until actual content is provided",
                        reply="I did not receive the content to skip ahead with. Please include the hypothesis or hint itself.",
                    ),
                ),
                Guard(
                    name="skip_signals_available",
                    predicate=_has_signals,
                    failure=GuardFailure(
                        reason="skip blocked until analysis signals exist",
                        reply="There is no analysis result yet, so I cannot ground a skipped hypothesis in anything. Analyze campaign metrics first.",
                    ),
                ),
            ),
            effects=(_materialize_skip,),
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
            guards=(
                Guard(
                    name="pending_approval_open",
                    predicate=_has_pending_approval,
                    failure=GuardFailure(
                        reason="approve-like intent blocked: nothing is pending approval",
                        reply="There is nothing pending approval right now, so I did not advance the workflow.",
                    ),
                ),
            ),
        ),
    ),
)
