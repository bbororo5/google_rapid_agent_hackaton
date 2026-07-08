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
    assert delta.reply is not None and "승인 대기" in delta.reply


def test_affirmative_reply_confirms_pending_proposal() -> None:
    # advisor가 던진 제안(pending_gate)에 사용자가 짧게 긍정하면, 그 제안이
    # 겨냥한 단계로만 넘어간다 — 형식적 승인 버튼과는 별개의, 좁은 확정 경로.
    # 확정은 해당 단계의 정식 규칙을 타므로 재료(신호)가 있어야 한다.
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
    state.phase_artifacts[PhaseType.DATA_ANALYSIS.value]["signals"] = [{"id": "sig_1"}]
    delta = ProposedChange(intent=TurnIntent.CHAT, response_mode=ResponseMode.DIRECT)

    decision = apply_proposed_change(state, delta, "yes please")

    assert decision.delegation_mode == DelegationMode.RERUN
    assert state.current_phase == PhaseType.HYPOTHESIS_GEN
    assert state.pending_gate is None


def test_gate_confirmation_respects_phase_guards() -> None:
    # 신호가 없는 상태에서 가설 제안을 긍정해도, 재료 가드에 막혀 단계가
    # 넘어가지 않는다 — 확정 경로가 가드를 우회하는 뒷문이 되면 안 된다.
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

    decision = apply_proposed_change(state, delta, "네 해주세요")

    assert decision.delegation_mode == DelegationMode.DIRECT
    assert state.current_phase == PhaseType.DATA_ANALYSIS
    assert state.pending_gate is None
    assert delta.reply is not None and "분석" in delta.reply


def test_new_request_with_trailing_hejwo_does_not_confirm_gate() -> None:
    # "확인해줘"처럼 '해줘'로 끝나는 새 요청은 긍정 확정이 아니다 — 마커를
    # 걷어낸 잔여물(요청 본문)이 남으므로 게이트는 리셋되고 정상 분류로 간다.
    state = ConversationState(
        current_phase=PhaseType.HYPOTHESIS_GEN,
        target_phase=PhaseType.HYPOTHESIS_GEN,
        revision=5,
        pending_gate=PendingProposal(
            target_phase=PhaseType.EXPERIMENT_PLAN,
            payload="실험 계획을 수립할까요?",
            created_turn=5,
        ),
    )
    state.phase_artifacts[PhaseType.DATA_ANALYSIS.value]["signals"] = [{"id": "sig_1"}]
    state.phase_artifacts[PhaseType.HYPOTHESIS_GEN.value]["hypotheses"] = [{"id": "hyp_1"}]
    delta = ProposedChange(intent=TurnIntent.CHAT, response_mode=ResponseMode.DIRECT)

    decision = apply_proposed_change(state, delta, "상위 포스트 목록을 바로 확인해줘")

    assert decision.delegation_mode == DelegationMode.DIRECT
    assert state.current_phase == PhaseType.HYPOTHESIS_GEN
    assert state.pending_gate is None


def test_pure_affirmative_with_fillers_confirms_gate() -> None:
    # "오 제발해줘"처럼 추임새만 섞인 순수 긍정은 확정이다.
    state = ConversationState(
        current_phase=PhaseType.DATA_ANALYSIS,
        target_phase=PhaseType.DATA_ANALYSIS,
        revision=5,
        pending_gate=PendingProposal(
            target_phase=PhaseType.HYPOTHESIS_GEN,
            payload="가설을 만들어 볼까요?",
            created_turn=5,
        ),
    )
    state.phase_artifacts[PhaseType.DATA_ANALYSIS.value]["signals"] = [{"id": "sig_1"}]
    delta = ProposedChange(intent=TurnIntent.CHAT, response_mode=ResponseMode.DIRECT)

    decision = apply_proposed_change(state, delta, "오 제발해줘")

    assert decision.delegation_mode == DelegationMode.RERUN
    assert state.current_phase == PhaseType.HYPOTHESIS_GEN


def test_negated_reply_does_not_confirm_pending_proposal() -> None:
    # "그건 말고" 같은 부정이 섞이면 마커("좋아" 등)가 있어도 확정하지 않는다.
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

    apply_proposed_change(state, delta, "좋아 근데 그건 말고 다른 거 먼저")

    assert state.current_phase == PhaseType.DATA_ANALYSIS
    assert state.pending_gate is None


def test_backtrack_asks_confirmation_then_executes_on_affirmative() -> None:
    # 되돌리기가 이후 산출물을 폐기하게 되면, 먼저 확인 카드를 세우고
    # (산출물 보존), 다음 턴의 짧은 긍정에서만 실제로 실행한다.
    state = ConversationState(
        current_phase=PhaseType.HYPOTHESIS_GEN,
        target_phase=PhaseType.HYPOTHESIS_GEN,
        revision=7,
    )
    state.phase_artifacts[PhaseType.DATA_ANALYSIS.value]["signals"] = [{"id": "sig_1"}]
    state.phase_artifacts[PhaseType.HYPOTHESIS_GEN.value]["hypotheses"] = [{"id": "hyp_1"}]
    delta = ProposedChange(
        intent=TurnIntent.BACKTRACK,
        response_mode=ResponseMode.RERUN,
        target_phase=PhaseType.DATA_ANALYSIS,
    )

    decision = apply_proposed_change(state, delta, "처음부터 다시 분석해줘")

    assert decision.delegation_mode == DelegationMode.CLARIFY
    assert state.pending_gate is not None and state.pending_gate.kind == "backtrack"
    assert state.phase_artifacts[PhaseType.HYPOTHESIS_GEN.value]  # 아직 폐기 안 됨
    assert delta.reply is not None and "폐기" in delta.reply

    confirm_delta = ProposedChange(intent=TurnIntent.CHAT, response_mode=ResponseMode.DIRECT)
    confirm = apply_proposed_change(state, confirm_delta, "네 진행해주세요")

    assert confirm.delegation_mode == DelegationMode.RERUN
    assert state.current_phase == PhaseType.DATA_ANALYSIS
    assert not state.phase_artifacts[PhaseType.HYPOTHESIS_GEN.value]
    assert state.pending_gate is None


def test_backtrack_without_downstream_artifacts_runs_immediately() -> None:
    # 폐기할 산출물이 없으면 확인 없이 바로 되돌린다.
    state = ConversationState(
        current_phase=PhaseType.HYPOTHESIS_GEN,
        target_phase=PhaseType.HYPOTHESIS_GEN,
        revision=7,
    )
    delta = ProposedChange(
        intent=TurnIntent.BACKTRACK,
        response_mode=ResponseMode.RERUN,
        target_phase=PhaseType.DATA_ANALYSIS,
    )

    decision = apply_proposed_change(state, delta, "분석 단계로 돌아가자")

    assert decision.delegation_mode == DelegationMode.RERUN
    assert state.current_phase == PhaseType.DATA_ANALYSIS
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
