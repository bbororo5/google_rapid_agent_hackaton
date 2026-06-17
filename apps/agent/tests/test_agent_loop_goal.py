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
    ResponseMode,
    ConversationState,
    ProposedChange,
    apply_proposed_change,
)


def test_approve_without_pending_approval_runs_next_phase() -> None:
    state = ConversationState(
        current_phase=PhaseType.HYPOTHESIS_GEN,
        target_phase=PhaseType.HYPOTHESIS_GEN,
    )
    delta = ProposedChange(intent=TurnIntent.APPROVE, response_mode=ResponseMode.DIRECT)

    decision = apply_proposed_change(state, delta, "yes, continue")

    assert decision.delegation_mode == DelegationMode.RERUN
    assert state.current_phase == PhaseType.EXPERIMENT_PLAN
    assert state.target_phase == PhaseType.EXPERIMENT_PLAN


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
