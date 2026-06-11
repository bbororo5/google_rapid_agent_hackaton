"""Delegation-mode routing for interpreted turns."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app import tracing
from app.orchestration.emitter import StreamEmitter
from app.orchestration.models import TurnContext, TurnDecision, TurnOutcome
from app.orchestration.phases import PhaseRunnerRegistry, analysis_window, baseline_window
from app.runtime.restore import restore_from_episode
from app.runtime.state import DelegationMode, DeltaIntent, PhaseType
from app.tools import evidence

log = logging.getLogger("launchpilot.orchestration.router")

RouteHandler = Callable[[TurnContext, TurnDecision], Awaitable[TurnOutcome]]


class TurnRouter:
    """Declarative route table from delegation mode to behavior object method."""

    def __init__(self, emitter: StreamEmitter, phases: PhaseRunnerRegistry) -> None:
        self._emitter = emitter
        self._phases = phases
        self._routes: dict[DelegationMode, RouteHandler] = {
            DelegationMode.CLARIFY: self._clarify,
            DelegationMode.RERUN: self._rerun,
            DelegationMode.DELEGATE: self._delegate,
            DelegationMode.DIRECT: self._direct,
        }

    async def route(self, turn: TurnContext, decision: TurnDecision) -> TurnOutcome:
        handler = self._routes.get(decision.delegation.mode, self._direct)
        return await handler(turn, decision)

    async def _clarify(self, turn: TurnContext, decision: TurnDecision) -> TurnOutcome:
        reply = (
            decision.delta.clarification_question
            or decision.delta.reply
            or "I can do that, but please confirm the change first."
        )
        await self._emitter.assistant_text(turn.record, reply)
        return TurnOutcome({"mode": "clarify", "reply": reply[:500]})

    async def _rerun(self, turn: TurnContext, decision: TurnDecision) -> TurnOutcome:
        if not turn.scope:
            await self._emitter.system_error(
                turn.record,
                "Campaign context required",
                "campaign_id를 확인할 수 없어 분석을 시작하지 않았습니다. 같은 thread에 campaign_id를 포함해 다시 요청해 주세요.",
            )
            return TurnOutcome({"mode": "rerun", "status": "missing_campaign"})

        # Restore (ADR-005 Phase 4): a backtrack that names a past episode rebuilds
        # the live state from that checkpoint instead of re-running forward.
        restore_episode_id = decision.delta.mutation.get("restore_episode_id")
        if decision.delta.intent == DeltaIntent.BACKTRACK and restore_episode_id:
            return await self._restore(turn, str(restore_episode_id))
        if not turn.campaign_context:
            await self._emitter.system_error(
                turn.record,
                "Campaign context not found",
                f"campaign_id={turn.scope.campaign_id} 컨텍스트를 찾지 못해 분석을 시작하지 않았습니다.",
            )
            return TurnOutcome({"mode": "rerun", "status": "campaign_not_found"})

        current = analysis_window()
        baseline = baseline_window(current)
        phase = turn.record.state.current_phase
        with evidence.scope(
            turn.record.workspace_id,
            turn.record.campaign_id,
            current.start,
            current.end,
            baseline.start,
            baseline.end,
        ), tracing.chain_span(
            "launchpilot.orchestrator",
            input_value=turn.content[:2000],
            metadata={**turn.trace_metadata, "stage": "PIPELINE"},
            workspace_id=turn.record.workspace_id,
            campaign_id=turn.record.campaign_id,
        ) as pipeline_span:
            await self._emitter.progress(
                turn.record,
                "round.dispatch",
                f"Starting {phase.value} round",
                "running",
            )
            log.info(
                "round start thread=%s phase=%s window=%s..%s",
                turn.record.thread_id,
                phase.value,
                current.start,
                current.end,
            )
            outcome = await self._phases.get(phase).run(turn)
            tracing.set_output(pipeline_span, outcome.trace_output)
            await self._emitter.progress(
                turn.record,
                "round.dispatch",
                f"Finished {phase.value} round",
                "done",
            )
        return outcome

    async def _restore(self, turn: TurnContext, episode_id: str) -> TurnOutcome:
        episode = await turn.repository.get_episode(episode_id)
        if episode is None:
            await self._emitter.system_error(
                turn.record,
                "Checkpoint not found",
                f"복원할 에피소드(episode_id={episode_id})를 찾지 못해 상태를 되돌리지 않았습니다.",
            )
            return TurnOutcome({"mode": "restore", "status": "episode_not_found"})
        await restore_from_episode(turn.record.state, episode, turn.repository)
        phase = turn.record.state.current_phase
        await self._emitter.assistant_text(
            turn.record,
            f"{phase.value} 시점({episode_id})으로 상태를 되돌렸습니다. 이어서 진행할 수 있습니다.",
        )
        return TurnOutcome({"mode": "restore", "phase": phase.value, "episode_id": episode_id})

    async def _delegate(self, turn: TurnContext, decision: TurnDecision) -> TurnOutcome:
        reply = (
            "요청은 현재 단계의 산출물 수정으로 분류했습니다. "
            "세부 phase agent는 다음 구현 범위라서, 지금은 오케스트레이터가 상태와 수정 의도만 안전하게 기록합니다."
        )
        turn.record.state.active_chat_history.append({"role": "assistant", "content": reply})
        await self._emitter.assistant_text(turn.record, reply)
        return TurnOutcome({"mode": "delegate", "target_phase": decision.delegation.target_phase.value})

    async def _direct(self, turn: TurnContext, decision: TurnDecision) -> TurnOutcome:
        reply = (
            self._artifact_lookup_reply(turn, decision.delta.intent)
            or decision.delta.reply
            or "How can I help with your campaign analysis?"
        )
        turn.record.state.active_chat_history.append({"role": "assistant", "content": reply})
        log.info("chat reply thread=%s context=%s", turn.record.thread_id, turn.state_hint)
        await self._emitter.assistant_text(turn.record, reply)
        return TurnOutcome({"mode": "direct", "reply": reply[:500]})

    def _artifact_lookup_reply(self, turn: TurnContext, intent: DeltaIntent) -> str | None:
        if intent != DeltaIntent.ARTIFACT_QUERY:
            return None

        raw_plan: Any = turn.record.state.phase_artifacts.get(PhaseType.EXPERIMENT_PLAN.value, {}).get(
            "experiment_plan"
        )
        if not isinstance(raw_plan, dict):
            return "아직 이 thread에서 확인할 수 있는 승인된 실험 계획이 없습니다."

        title = raw_plan.get("summary") or raw_plan.get("id") or "승인된 실험 계획"
        items = raw_plan.get("items") if isinstance(raw_plan.get("items"), list) else []
        if not items:
            return f"승인된 내용은 `{title}` 실험 계획입니다. 세부 실험 항목은 현재 runtime artifact에서 확인되지 않습니다."

        lines = [f"승인한 내용은 `{title}` 기준의 실험 계획입니다."]
        for index, item in enumerate(items[:3], start=1):
            if not isinstance(item, dict):
                continue
            item_title = item.get("title") or item.get("id") or f"실험 {index}"
            detail = f"{index}. {item_title}"
            if item.get("channel"):
                detail += f" ({item['channel']})"
            if item.get("scheduled_at"):
                detail += f", scheduled_at={item['scheduled_at']}"
            if item.get("success_criteria"):
                detail += f", success={item['success_criteria']}"
            lines.append(detail)
        return "\n".join(lines)
