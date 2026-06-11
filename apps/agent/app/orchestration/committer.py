"""State commit service for interpreted turns."""

from __future__ import annotations

from app import tracing
from app.orchestration.emitter import StreamEmitter
from app.orchestration.models import TurnContext, TurnDecision
from app.runtime.repository import DeltaEvent, RepositoryConflict


class StateCommitter:
    def __init__(self, emitter: StreamEmitter) -> None:
        self._emitter = emitter

    async def commit(self, turn: TurnContext, decision: TurnDecision, span) -> None:
        if not turn.scope:
            return
        await self._emitter.progress(turn.record, "state.commit", "Saving thread state", "running")
        event = DeltaEvent(
            scope=turn.scope,
            proposal=decision.delta,
            reducer_decision={
                "decision": decision.reducer.decision.value,
                "delegation_mode": decision.reducer.delegation_mode.value,
                "reason": decision.reducer.reason,
                "revision_before": decision.reducer.revision_before,
                "revision_after": decision.reducer.revision_after,
            },
        )
        try:
            await turn.repository.commit_state(turn.expected_revision, turn.record.state, event)
            # Refresh the Redis hot tier so the next turn reads the live copy
            # without an Elastic round-trip (ADR-005). ES remains authoritative.
            await turn.hot_store.put_state(turn.record.thread_id, turn.record.state)
            tracing.set_metadata(span, {"agent.state_delta.delta_id": event.delta_id})
            await self._emitter.progress(turn.record, "state.commit", "Saved thread state", "done", event.delta_id)
        except RepositoryConflict:
            tracing.set_metadata(span, {"agent.repository.conflict": True})
            await self._emitter.progress(turn.record, "state.commit", "Thread state changed elsewhere", "failed")
            await self._emitter.system_error(
                turn.record,
                "Agent busy",
                "동일 thread의 상태가 먼저 갱신되어 이번 턴의 상태 저장을 중단했습니다. 잠시 후 다시 시도해 주세요.",
            )
