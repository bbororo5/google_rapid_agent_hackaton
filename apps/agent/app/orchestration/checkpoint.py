"""Episode checkpointing for interpreted turns (ADR-005, Phase 2).

Episodes are persisted at semantic boundaries, not every turn (write-back):
- a phase round completed and advanced (FORWARD),
- a decision event: APPROVE / REJECT / BACKTRACK.

The state snapshot in each episode makes it a restore point. Python builds the
episode here; the runtime repository persists it.
"""
from __future__ import annotations

from app import tracing
from app.orchestration.emitter import StreamEmitter
from app.orchestration.models import TurnContext, TurnDecision, TurnOutcome
from app.runtime.episode import EpisodeOutcome, build_episode
from app.runtime.state import DeltaIntent


class Checkpointer:
    def __init__(self, emitter: StreamEmitter) -> None:
        self._emitter = emitter

    def _outcome_for(self, decision: TurnDecision, route_outcome: TurnOutcome) -> EpisodeOutcome | None:
        intent = decision.delta.intent
        if intent == DeltaIntent.BACKTRACK:
            return EpisodeOutcome.BACKTRACK
        if intent == DeltaIntent.APPROVE:
            return EpisodeOutcome.APPROVE
        if intent == DeltaIntent.REJECT:
            return EpisodeOutcome.REJECT
        if self._phase_round_completed(route_outcome):
            return EpisodeOutcome.FORWARD
        return None

    @staticmethod
    def _phase_round_completed(route_outcome: TurnOutcome) -> bool:
        # A phase runner returns trace_output with a "phase" key. Missing-input
        # guards carry a "status"; a failed reviewer gate carries
        # validator_passed False. Neither is a clean phase boundary.
        out = route_outcome.trace_output
        return (
            "phase" in out
            and "status" not in out
            and out.get("validator_passed") is not False
        )

    async def maybe_checkpoint(
        self,
        turn: TurnContext,
        decision: TurnDecision,
        route_outcome: TurnOutcome,
        span,
    ) -> None:
        if not turn.scope or turn.record.state.scope is None:
            return
        outcome = self._outcome_for(decision, route_outcome)
        if outcome is None:
            return
        episode = build_episode(
            turn.record.state,
            outcome,
            turn.record.state.active_chat_history,
            key_params=dict(decision.delta.mutation),
        )
        episode_id = await turn.repository.save_episode(episode)
        tracing.set_metadata(
            span,
            {"agent.episode.id": episode_id, "agent.episode.outcome": outcome.value},
        )
        await self._emitter.progress(
            turn.record,
            "episode.checkpoint",
            "Saved episode checkpoint",
            "done",
            f"{outcome.value}:{episode_id}",
        )
