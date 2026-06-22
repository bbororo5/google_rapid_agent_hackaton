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
            or "I can do that, but please confirm the change first."
        )
        await self._emitter.assistant_text(turn.record, reply)
        return TurnOutcome({"mode": "clarify", "reply": reply[:500]})

    async def _rerun(self, turn: TurnContext, decision: TurnDecision) -> TurnOutcome:
        if not turn.scope:
            await self._emitter.system_error(
                turn.record,
                "Campaign context required",
                "I could not find a campaign_id, so analysis did not start. Send the request again with a campaign_id in the same thread.",
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
                "Campaign context not found",
                f"I could not find context for campaign_id={turn.scope.campaign_id}, so analysis did not start.",
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
            telemetry.record_pipeline_outcome(pipeline_span, outcome.trace_output)
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
                f"I could not find episode_id={episode_id}, so the state was not restored.",
            )
            return TurnOutcome({"mode": "restore", "status": "episode_not_found"})
        await restore_from_episode(turn.record.state, episode, turn.repository)
        phase = turn.record.state.current_phase
        await self._emitter.assistant_text(
            turn.record,
            f"State was restored to {phase.value} at episode_id={episode_id}. You can continue from there.",
        )
        return TurnOutcome({"mode": "restore", "phase": phase.value, "episode_id": episode_id})

    async def _delegate(self, turn: TurnContext, decision: TurnDecision) -> TurnOutcome:
        reply = (
            "I classified this as an artifact revision for the current phase. "
            "Detailed phase-level editing is not implemented yet, so I recorded the requested change safely for now."
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

    def _artifact_lookup_reply(self, turn: TurnContext, intent: TurnIntent) -> str | None:
        if intent != TurnIntent.ARTIFACT_QUERY:
            return None

        raw_plan: Any = turn.record.state.phase_artifacts.get(PhaseType.EXPERIMENT_PLAN.value, {}).get(
            "experiment_plan"
        )
        if not isinstance(raw_plan, dict):
            return "There is no approved experiment plan available in this thread yet."

        title = raw_plan.get("summary") or raw_plan.get("id") or "approved experiment plan"
        items = raw_plan.get("items") if isinstance(raw_plan.get("items"), list) else []
        if not items:
            return f"The approved item is the `{title}` experiment plan. Detailed experiment items are not available in the runtime artifact."

        lines = [f"The approved output is the `{title}` experiment plan."]
        for index, item in enumerate(items[:3], start=1):
            if not isinstance(item, dict):
                continue
            item_title = item.get("title") or item.get("id") or f"Experiment {index}"
            detail = f"{index}. {item_title}"
            if item.get("channel"):
                detail += f" ({item['channel']})"
            if item.get("scheduled_at"):
                detail += f", scheduled_at={item['scheduled_at']}"
            if item.get("success_criteria"):
                detail += f", success={item['success_criteria']}"
            lines.append(detail)
        return "\n".join(lines)
