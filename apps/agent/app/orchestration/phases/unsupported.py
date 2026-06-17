"""평가 라운드: 아직 미구현. 안내만 하고 끝낸다."""
from __future__ import annotations

from app.orchestration.models import TurnContext, TurnOutcome
from app.orchestration.phases.base import BasePhaseRunner
from app.runtime.state import PhaseType


class UnsupportedPhaseRunner(BasePhaseRunner):
    """실험 평가 단계: 실행 결과 입력 후 분석 라운드에서 다룬다(아직 미구현)."""

    phase = PhaseType.EXPERIMENT_EVAL

    async def run(self, turn: TurnContext) -> TurnOutcome:
        await self.emitter.assistant_text(
            turn.record,
            "실험 평가 단계는 아직 실행 결과 입력 후 분석 라운드에서 다룹니다.",
        )
        return TurnOutcome({"mode": "phase_not_implemented", "phase": self.phase.value})
