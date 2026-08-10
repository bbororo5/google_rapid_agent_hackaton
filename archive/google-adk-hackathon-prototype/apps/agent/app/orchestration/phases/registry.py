"""단계 선택표: phase 값 -> 그 단계를 실행할 러너 객체.

if/switch 없이 사전(dict)에서 러너를 꺼낸다. 단계가 늘면 여기 한 줄만 추가한다.
"""
from __future__ import annotations

from app.orchestration.emitter import StreamEmitter
from app.orchestration.phases.analysis import AnalysisRoundRunner
from app.orchestration.phases.base import PhaseArtifactStore, PhaseRunner
from app.orchestration.phases.hypothesis import HypothesisRoundRunner
from app.orchestration.phases.plan import PlanRoundRunner
from app.orchestration.phases.unsupported import UnsupportedPhaseRunner
from app.runtime.state import PhaseType


class PhaseRunnerRegistry:
    """Declarative phase selection: phase enum -> runner object."""

    def __init__(self, emitter: StreamEmitter) -> None:
        artifacts = PhaseArtifactStore()
        self._runners: dict[PhaseType, PhaseRunner] = {
            PhaseType.DATA_ANALYSIS: AnalysisRoundRunner(emitter, artifacts),
            PhaseType.HYPOTHESIS_GEN: HypothesisRoundRunner(emitter, artifacts),
            PhaseType.EXPERIMENT_PLAN: PlanRoundRunner(emitter, artifacts),
            PhaseType.EXPERIMENT_EVAL: UnsupportedPhaseRunner(emitter, artifacts),
        }

    def get(self, phase: PhaseType) -> PhaseRunner:
        return self._runners.get(phase, self._runners[PhaseType.EXPERIMENT_EVAL])
