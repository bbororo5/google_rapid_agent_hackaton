"""State commit service for interpreted turns."""

from __future__ import annotations

from app import telemetry
from app.orchestration.emitter import StreamEmitter
from app.orchestration.models import TurnContext, TurnDecision
from app.runtime.repository import ChangeLogEntry, RepositoryConflict


class StateCommitter:
    def __init__(self, emitter: StreamEmitter) -> None:
        self._emitter = emitter

    async def commit(self, turn: TurnContext, decision: TurnDecision, span) -> None:
        # 목표: 이번 턴에서 바뀐 상태를 영구 저장하고 캐시를 갱신한다.
        #       (스코프가 없으면 저장할 게 없으니 그냥 끝낸다.)
        if not turn.scope:
            return
        await self._emitter.progress(turn.record, "state.commit", "Saving thread state", "running")
        # 1) 변경 이력 한 건(누가/무엇을/왜 바꿨는지)을 만든다.
        event = ChangeLogEntry(
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
            # 2) 권위 저장소에 기록한다. (내가 본 revision과 다르면 충돌로 막힌다.)
            await turn.repository.commit_state(turn.expected_revision, turn.record.state, event)
            # 3) 캐시(Redis)도 최신으로 갱신해 다음 턴이 Elastic 왕복 없이 읽게 한다.
            #    권위는 여전히 Elastic (ADR-005).
            await turn.state_cache.put_state(turn.record.thread_id, turn.record.state)
            telemetry.record_state_delta(span, event.delta_id)
            await self._emitter.progress(turn.record, "state.commit", "Saved thread state", "done", event.delta_id)
        except RepositoryConflict:
            # 4) 그 사이 다른 턴이 먼저 상태를 바꿨음 -> 저장 중단하고 재시도 안내.
            telemetry.record_repository_conflict(span)
            await self._emitter.progress(turn.record, "state.commit", "Thread state changed elsewhere", "failed")
            await self._emitter.system_error(
                turn.record,
                "Agent busy",
                "This thread was updated by another turn first, so this turn was not saved. Please try again shortly.",
            )
