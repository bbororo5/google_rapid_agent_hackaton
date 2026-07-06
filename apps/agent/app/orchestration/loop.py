"""Goal-oriented turn loop for orchestration."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.agents import workers
from app.orchestration.context import PromptContextBuilder
from app.orchestration.emitter import StreamEmitter
from app.orchestration.goals import GoalKind, TurnGoal
from app.orchestration.models import TurnContext, TurnDecision, TurnOutcome
from app.orchestration.router import TurnRouter
from app.runtime.state import DelegationMode, PendingProposal, PhaseType

_SUGGESTIBLE_PHASES = {PhaseType.DATA_ANALYSIS, PhaseType.HYPOTHESIS_GEN}
_SUGGESTED_PHASE_BY_NAME = {
    "HYPOTHESIS_GEN": PhaseType.HYPOTHESIS_GEN,
    "EXPERIMENT_PLAN": PhaseType.EXPERIMENT_PLAN,
}

log = logging.getLogger("launchpilot.orchestration.loop")


@dataclass(slots=True)
class LoopState:
    goal: TurnGoal
    started_at: float = field(default_factory=time.monotonic)
    steps: int = 0
    llm_calls: int = 0
    phase_runs: int = 0
    observations: list[dict[str, Any]] = field(default_factory=list)

    def observe(self, kind: str, payload: dict[str, Any]) -> None:
        self.steps += 1
        self.observations.append({"kind": kind, **payload})

    def trace(self, outcome: TurnOutcome | None = None) -> dict[str, Any]:
        return {
            "goal": self.goal.model_dump(mode="json"),
            "steps": self.steps,
            "llm_calls": self.llm_calls,
            "phase_runs": self.phase_runs,
            "elapsed_ms": int((time.monotonic() - self.started_at) * 1000),
            "observations": self.observations,
            "route_outcome": outcome.trace_output if outcome else None,
        }


class AgentLoop:
    """Small goal loop around routing, advisor response, and observations."""

    def __init__(
        self,
        emitter: StreamEmitter,
        router: TurnRouter,
        prompts: PromptContextBuilder,
    ) -> None:
        self._emitter = emitter
        self._router = router
        self._prompts = prompts

    async def run(self, turn: TurnContext, decision: TurnDecision, goal: TurnGoal) -> TurnOutcome:
        state = LoopState(goal=goal)
        await self._emitter.progress(
            turn.record,
            "goal.plan",
            "Planning agent goal",
            "done",
            f"{goal.kind.value} / {goal.budget_profile.value}",
        )
        log.info(
            "goal start thread=%s kind=%s profile=%s max_steps=%s max_llm=%s",
            turn.record.thread_id,
            goal.kind.value,
            goal.budget_profile.value,
            goal.budgets.max_steps,
            goal.budgets.max_llm_calls,
        )

        if goal.kind == GoalKind.ANSWER_QUESTION and decision.delegation.mode == DelegationMode.DIRECT:
            reply = await self._advisor_reply(turn, decision, state)
            return TurnOutcome({"mode": "agent_loop", "reply": reply[:500], **state.trace()})

        route_outcome = await self._router.route(turn, decision)
        state.phase_runs += 1 if decision.delegation.mode == DelegationMode.RERUN else 0
        state.observe("route", route_outcome.trace_output)

        if self._should_follow_up(turn, decision, goal, route_outcome, state):
            reply = await self._advisor_reply(turn, decision, state, route_outcome)
            state.observe("advisor_follow_up", {"reply_preview": reply[:160]})

        return TurnOutcome(
            {
                "mode": "agent_loop",
                **state.trace(route_outcome),
            },
            commit_state=route_outcome.commit_state,
        )

    def _should_follow_up(
        self,
        turn: TurnContext,
        decision: TurnDecision,
        goal: TurnGoal,
        outcome: TurnOutcome,
        state: LoopState,
    ) -> bool:
        if state.llm_calls >= goal.budgets.max_llm_calls:
            return False
        if goal.kind in {GoalKind.CLARIFY, GoalKind.APPROVAL_ACTION}:
            return False
        if decision.delegation.mode == DelegationMode.RERUN:
            return True
        if outcome.trace_output.get("status", "").startswith("missing_"):
            return True
        return goal.kind == GoalKind.REVISE_ARTIFACT

    async def _advisor_reply(
        self,
        turn: TurnContext,
        decision: TurnDecision,
        state: LoopState,
        outcome: TurnOutcome | None = None,
    ) -> str:
        await self._emitter.progress(
            turn.record,
            "advisor.respond",
            "Thinking through the response",
            "running",
            f"budget {state.llm_calls + 1}/{state.goal.budgets.max_llm_calls}",
        )
        context = self._prompts.build_interpreter_context(turn)
        prompt = (
            "[output_language]\n"
            "English only. Do not answer in French, Korean, or any other non-English language."
            "\n\n"
            "[goal]\n"
            + json.dumps(state.goal.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
            + "\n\n[decision]\n"
            + json.dumps(decision.trace_metadata, ensure_ascii=False, sort_keys=True)
            + "\n\n[route_outcome]\n"
            + json.dumps(outcome.trace_output if outcome else {}, ensure_ascii=False, sort_keys=True)
            + "\n\n[full_runtime_context]\n"
            + context
            + "\n\n[user]\n"
            + turn.content
        )
        state.llm_calls += 1
        emitted_delta = False

        async def emit_delta(delta: str) -> None:
            nonlocal emitted_delta
            emitted_delta = True
            await self._emitter.assistant_text(turn.record, delta)

        reply = await workers.run_advisor(turn.content, prompt, on_delta=emit_delta)
        turn.record.state.active_chat_history.append({"role": "assistant", "content": reply})
        if not emitted_delta:
            await self._emitter.assistant_text(turn.record, reply)
        await self._emitter.progress(
            turn.record,
            "advisor.respond",
            "Responded from full context",
            "done",
        )
        state.observe("advisor", {"reply_preview": reply[:160]})
        await self._scout_for_suggestion(turn, state)
        return reply

    async def _scout_for_suggestion(self, turn: TurnContext, state: LoopState) -> None:
        # advisor가 자연어로 다음 단계를 제안했는지 별도로 확인한다 (스트리밍은
        # advisor 응답 그대로 두고, 이 판정만 뒤따라 붙는다). 이미 대기중인
        # 제안이 있거나, 제안할 만한 단계가 아니면 부르지 않는다.
        conv_state = turn.record.state
        if conv_state.pending_gate is not None:
            return
        if conv_state.current_phase not in _SUGGESTIBLE_PHASES:
            return
        if state.llm_calls >= state.goal.budgets.max_llm_calls:
            return
        last_reply = next(
            (m["content"] for m in reversed(conv_state.active_chat_history) if m["role"] == "assistant"),
            None,
        )
        if not last_reply:
            return
        state.llm_calls += 1
        scouted = await workers.run_suggestion_scout(last_reply)
        target = _SUGGESTED_PHASE_BY_NAME.get(scouted.get("target_phase") or "")
        if scouted.get("suggests_entry") and target is not None:
            conv_state.pending_gate = PendingProposal(
                target_phase=target,
                payload=scouted.get("payload") or last_reply[:200],
                created_turn=conv_state.revision,
            )
