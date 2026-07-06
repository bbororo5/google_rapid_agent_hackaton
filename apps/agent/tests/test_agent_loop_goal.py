from __future__ import annotations

from types import SimpleNamespace

from app.orchestration.goals import BudgetProfile, GoalController
from app.orchestration.models import TurnDecision
from app.runtime.state import (
    DelegationDecision,
    DelegationMode,
    TurnIntent,
    PhaseType,
    ChangeDecision,
    ChangeDecisionType,
    PendingProposal,
    ResponseMode,
    ConversationState,
    ProposedChange,
    apply_proposed_change,
)


def test_approve_without_pending_approval_or_gate_stays_direct() -> None:
    # 이전엔 승인할 대상이 없어도 APPROVE로 분류되면 무조건 다음 단계로
    # 넘어갔다 (issue #25의 "예상치 못한 가설 단계 진입"과 같은 위험군).
    # 이제는 실제로 열려있는 승인(pending_approval_id)이나 확정 직전 제안
    # (pending_gate)이 없으면 넘어가지 않는다.
    state = ConversationState(
        current_phase=PhaseType.HYPOTHESIS_GEN,
        target_phase=PhaseType.HYPOTHESIS_GEN,
    )
    delta = ProposedChange(intent=TurnIntent.APPROVE, response_mode=ResponseMode.DIRECT)

    decision = apply_proposed_change(state, delta, "yes, continue")

    assert decision.delegation_mode == DelegationMode.DIRECT
    assert state.current_phase == PhaseType.HYPOTHESIS_GEN
    assert state.target_phase == PhaseType.HYPOTHESIS_GEN
    assert delta.reply is not None and "nothing pending approval" in delta.reply


def test_affirmative_reply_confirms_pending_proposal() -> None:
    # advisor가 던진 제안(pending_gate)에 사용자가 짧게 긍정하면, 그 제안이
    # 겨냥한 단계로만 넘어간다 — 형식적 승인 버튼과는 별개의, 좁은 확정 경로.
    state = ConversationState(
        current_phase=PhaseType.DATA_ANALYSIS,
        target_phase=PhaseType.DATA_ANALYSIS,
        revision=5,
        pending_gate=PendingProposal(
            target_phase=PhaseType.HYPOTHESIS_GEN,
            payload="Shall I generate hypotheses from these signals?",
            created_turn=5,
        ),
    )
    delta = ProposedChange(intent=TurnIntent.CHAT, response_mode=ResponseMode.DIRECT)

    decision = apply_proposed_change(state, delta, "yes please")

    assert decision.delegation_mode == DelegationMode.RERUN
    assert state.current_phase == PhaseType.HYPOTHESIS_GEN
    assert state.pending_gate is None


def test_unrelated_reply_expires_pending_proposal_without_advancing() -> None:
    state = ConversationState(
        current_phase=PhaseType.DATA_ANALYSIS,
        target_phase=PhaseType.DATA_ANALYSIS,
        revision=5,
        pending_gate=PendingProposal(
            target_phase=PhaseType.HYPOTHESIS_GEN,
            payload="Shall I generate hypotheses from these signals?",
            created_turn=5,
        ),
    )
    delta = ProposedChange(intent=TurnIntent.CHAT, response_mode=ResponseMode.DIRECT)

    apply_proposed_change(state, delta, "what was last month's result?")

    assert state.current_phase == PhaseType.DATA_ANALYSIS
    assert state.pending_gate is None


def test_approve_with_pending_approval_stays_direct() -> None:
    state = ConversationState(
        current_phase=PhaseType.EXPERIMENT_PLAN,
        target_phase=PhaseType.EXPERIMENT_PLAN,
        pending_approval_id="approval_1",
    )
    delta = ProposedChange(intent=TurnIntent.APPROVE, response_mode=ResponseMode.DIRECT)

    decision = apply_proposed_change(state, delta, "approve")

    assert decision.delegation_mode == DelegationMode.DIRECT
    assert state.current_phase == PhaseType.EXPERIMENT_EVAL
    assert state.target_phase == PhaseType.EXPERIMENT_EVAL


def test_goal_controller_uses_deep_budget_for_deep_requests() -> None:
    controller = GoalController()
    delta = ProposedChange(intent=TurnIntent.CHAT, response_mode=ResponseMode.DIRECT)
    reducer = ChangeDecision(
        decision=ChangeDecisionType.ACCEPTED,
        delegation_mode=DelegationMode.DIRECT,
        state=ConversationState(),
        reason="direct",
        delta=delta,
        revision_before=0,
        revision_after=1,
    )
    decision = TurnDecision(
        delta=delta,
        reducer=reducer,
        delegation=DelegationDecision(
            mode=DelegationMode.DIRECT,
            target_phase=PhaseType.DATA_ANALYSIS,
            reason="direct",
        ),
    )
    turn = SimpleNamespace(content="Explain this as thoroughly as possible")

    goal = controller.create(turn, decision)

    assert goal.budget_profile == BudgetProfile.DEEP_ANALYSIS
    assert goal.budgets.max_steps >= 40
