"""제안-확인(propose-confirm) 골든 테스트.

advisor 응답 뒤에 붙는 suggestion scout이 pending_gate를 언제 세우고, 언제
안 세우는지를 잠근다. 실제 Gemini 호출 없이 workers.run_suggestion_scout만
monkeypatch한다.
"""
from __future__ import annotations

import pytest

from app.orchestration import loop as loop_module
from app.orchestration.emitter import StreamEmitter
from app.orchestration.goals import BudgetProfile, GoalBudget, GoalKind, TurnGoal
from app.orchestration.loop import AgentLoop, LoopState
from app.orchestration.models import TurnContext
from app.runtime.repository import InMemoryAgentRuntimeRepository
from app.runtime.state import PendingProposal, PhaseType, ScopeContext
from app.runtime.state_cache import get_state_cache
from app.runtime.thread_store import ThreadRecord


def _turn() -> TurnContext:
    scope = ScopeContext(workspace_id="demo_workspace", campaign_id="camp_1", thread_id="thread_x")
    record = ThreadRecord(thread_id="thread_x", workspace_id="demo_workspace", campaign_id="camp_1")
    record.state.scope = scope
    return TurnContext(
        record=record,
        content="hi",
        attachments=(),
        repository=InMemoryAgentRuntimeRepository(),
        state_cache=get_state_cache(),
        scope=scope,
    )


def _loop_state() -> LoopState:
    goal = TurnGoal(
        kind=GoalKind.ANSWER_QUESTION,
        user_request="hi",
        target_phase=PhaseType.DATA_ANALYSIS,
        budget_profile=BudgetProfile.INTERACTIVE_QUICK,
        budgets=GoalBudget(max_steps=6, max_llm_calls=3, max_phase_runs=1, max_repairs=1, max_seconds=60),
    )
    return LoopState(goal=goal)


def _agent_loop() -> AgentLoop:
    return AgentLoop(StreamEmitter(), router=None, prompts=None)  # 이 메서드는 router/prompts를 안 씀


async def test_scout_sets_pending_gate_when_suggested(monkeypatch: pytest.MonkeyPatch) -> None:
    turn = _turn()
    turn.record.state.active_chat_history.append(
        {"role": "assistant", "content": "Would you like me to generate hypotheses?"}
    )

    async def fake_scout(reply: str) -> dict:
        return {"suggests_entry": True, "target_phase": "HYPOTHESIS_GEN", "payload": "generate hypotheses?"}

    monkeypatch.setattr(loop_module.workers, "run_suggestion_scout", fake_scout)

    await _agent_loop()._scout_for_suggestion(turn, _loop_state())

    gate = turn.record.state.pending_gate
    assert gate is not None
    assert gate.target_phase == PhaseType.HYPOTHESIS_GEN
    assert gate.payload == "generate hypotheses?"


async def test_scout_does_not_run_when_gate_already_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    turn = _turn()
    turn.record.state.active_chat_history.append({"role": "assistant", "content": "reply"})
    turn.record.state.pending_gate = PendingProposal(
        target_phase=PhaseType.HYPOTHESIS_GEN, payload="already pending", created_turn=0
    )

    called = False

    async def fake_scout(reply: str) -> dict:
        nonlocal called
        called = True
        return {"suggests_entry": True, "target_phase": "HYPOTHESIS_GEN"}

    monkeypatch.setattr(loop_module.workers, "run_suggestion_scout", fake_scout)

    await _agent_loop()._scout_for_suggestion(turn, _loop_state())

    assert called is False
    assert turn.record.state.pending_gate.payload == "already pending"


async def test_scout_skips_outside_suggestible_phases(monkeypatch: pytest.MonkeyPatch) -> None:
    turn = _turn()
    turn.record.state.current_phase = PhaseType.EXPERIMENT_PLAN
    turn.record.state.active_chat_history.append({"role": "assistant", "content": "reply"})

    called = False

    async def fake_scout(reply: str) -> dict:
        nonlocal called
        called = True
        return {"suggests_entry": True, "target_phase": "HYPOTHESIS_GEN"}

    monkeypatch.setattr(loop_module.workers, "run_suggestion_scout", fake_scout)

    await _agent_loop()._scout_for_suggestion(turn, _loop_state())

    assert called is False
    assert turn.record.state.pending_gate is None


async def test_scout_ignores_non_entry_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    turn = _turn()
    turn.record.state.active_chat_history.append({"role": "assistant", "content": "Last month's save rate was 12%."})

    async def fake_scout(reply: str) -> dict:
        return {"suggests_entry": False}

    monkeypatch.setattr(loop_module.workers, "run_suggestion_scout", fake_scout)

    await _agent_loop()._scout_for_suggestion(turn, _loop_state())

    assert turn.record.state.pending_gate is None
