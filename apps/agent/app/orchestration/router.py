"""Delegation-mode routing for interpreted turns."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app import telemetry
from app.orchestration.emitter import StreamEmitter
from app.orchestration.models import TurnContext, TurnDecision, TurnOutcome
from app.orchestration.phases import PhaseRunnerRegistry, analysis_window, baseline_window
from app.runtime.restore import restore_from_episode
from app.runtime.state import DelegationMode, TurnIntent, PhaseType
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
            or "진행할 수 있어요. 다만 변경 내용을 먼저 확인해 주세요."
        )
        await self._emitter.assistant_text(turn.record, reply)
        return TurnOutcome({"mode": "clarify", "reply": reply[:500]})

    async def _rerun(self, turn: TurnContext, decision: TurnDecision) -> TurnOutcome:
        if not turn.scope:
            await self._emitter.system_error(
                turn.record,
                "캠페인 컨텍스트 필요",
                "campaign_id를 찾지 못해 분석을 시작하지 못했어요. 같은 스레드에서 campaign_id와 함께 다시 요청해 주세요.",
            )
            return TurnOutcome({"mode": "rerun", "status": "missing_campaign"})

        # Restore (ADR-005 Phase 4): a backtrack that names a past episode rebuilds
        # the live state from that checkpoint instead of re-running forward.
        restore_episode_id = decision.delta.mutation.get("restore_episode_id")
        if decision.delta.intent == TurnIntent.BACKTRACK and restore_episode_id:
            return await self._restore(turn, str(restore_episode_id))
        if not turn.campaign_context:
            await self._emitter.system_error(
                turn.record,
                "캠페인 컨텍스트를 찾을 수 없음",
                f"campaign_id={turn.scope.campaign_id}의 컨텍스트를 찾지 못해 분석을 시작하지 못했어요.",
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
        ), telemetry.pipeline_span(
            turn.content,
            metadata=turn.trace_metadata,
            workspace_id=turn.record.workspace_id,
            campaign_id=turn.record.campaign_id,
        ) as pipeline_span:
            await self._emitter.progress(
                turn.record,
                "round.dispatch",
                f"{phase.value} 라운드 시작",
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
            telemetry.record_pipeline_outcome(pipeline_span, outcome.trace_output)
            await self._emitter.progress(
                turn.record,
                "round.dispatch",
                f"{phase.value} 라운드 완료",
                "done",
            )
        return outcome

    async def _restore(self, turn: TurnContext, episode_id: str) -> TurnOutcome:
        episode = await turn.repository.get_episode(episode_id)
        if episode is None:
            await self._emitter.system_error(
                turn.record,
                "체크포인트를 찾을 수 없음",
                f"episode_id={episode_id}를 찾지 못해 상태를 되돌리지 못했어요.",
            )
            return TurnOutcome({"mode": "restore", "status": "episode_not_found"})
        await restore_from_episode(turn.record.state, episode, turn.repository)
        phase = turn.record.state.current_phase
        await self._emitter.assistant_text(
            turn.record,
            f"상태를 episode_id={episode_id}의 {phase.value} 단계로 되돌렸어요. 이어서 진행하실 수 있어요.",
        )
        return TurnOutcome({"mode": "restore", "phase": phase.value, "episode_id": episode_id})

    async def _delegate(self, turn: TurnContext, decision: TurnDecision) -> TurnOutcome:
        reply = (
            "현재 단계 산출물에 대한 수정 요청으로 분류했어요. "
            "단계별 세부 편집은 아직 지원하지 않아, 요청하신 변경 내용을 우선 안전하게 기록해 두었어요."
        )
        turn.record.state.active_chat_history.append({"role": "assistant", "content": reply})
        await self._emitter.assistant_text(turn.record, reply)
        return TurnOutcome({"mode": "delegate", "target_phase": decision.delegation.target_phase.value})

    async def _direct(self, turn: TurnContext, decision: TurnDecision) -> TurnOutcome:
        reply = (
            self._artifact_lookup_reply(turn, decision.delta.intent)
            or decision.delta.reply
            or "캠페인 분석과 관련해 무엇을 도와드릴까요?"
        )
        turn.record.state.active_chat_history.append({"role": "assistant", "content": reply})
        log.info("chat reply thread=%s context=%s", turn.record.thread_id, turn.state_hint)
        await self._emitter.assistant_text(turn.record, reply)
        return TurnOutcome({"mode": "direct", "reply": reply[:500]})

    def _artifact_lookup_reply(self, turn: TurnContext, intent: TurnIntent) -> str | None:
        if intent != TurnIntent.ARTIFACT_QUERY:
            return None

        raw_plan: Any = turn.record.state.phase_artifacts.get(PhaseType.EXPERIMENT_PLAN.value, {}).get(
            "experiment_plan"
        )
        if not isinstance(raw_plan, dict):
            return "이 스레드에는 아직 승인된 실험 계획이 없어요."

        title = raw_plan.get("summary") or raw_plan.get("id") or "승인된 실험 계획"
        items = raw_plan.get("items") if isinstance(raw_plan.get("items"), list) else []
        if not items:
            return f"승인된 항목은 `{title}` 실험 계획이에요. 세부 실험 항목은 런타임 아티팩트에서 확인할 수 없어요."

        lines = [f"승인된 산출물은 `{title}` 실험 계획이에요."]
        for index, item in enumerate(items[:3], start=1):
            if not isinstance(item, dict):
                continue
            item_title = item.get("title") or item.get("id") or f"실험 {index}"
            detail = f"{index}. {item_title}"
            if item.get("channel"):
                detail += f" ({item['channel']})"
            if item.get("scheduled_at"):
                detail += f", 예정일: {item['scheduled_at']}"
            if item.get("success_criteria"):
                detail += f", 성공 기준: {item['success_criteria']}"
            lines.append(detail)
        return "\n".join(lines)
