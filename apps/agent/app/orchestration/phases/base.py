"""라운드 러너 공통 토대.

러너 인터페이스(PhaseRunner), 결과물 저장 도구(PhaseArtifactStore), 그리고 세
라운드(분석/가설/계획)가 공유하는 부모 클래스(BasePhaseRunner)를 모은다.
"""
from __future__ import annotations

import logging
from typing import Protocol

from app.contracts import Hypothesis, Signal
from app.orchestration.emitter import StreamEmitter
from app.orchestration.models import CancelledTurn, TurnContext, TurnOutcome
from app.runtime.repository import RuntimeArtifact
from app.runtime.state import PhaseType

log = logging.getLogger("launchpilot.orchestration.phases")


class PhaseRunner(Protocol):
    phase: PhaseType

    async def run(self, turn: TurnContext) -> TurnOutcome:
        ...


class PhaseArtifactStore:
    """단계 결과물을 저장소에 보관하고, 그 영수증(ref)을 상태에 최근 6건만 남긴다."""

    async def save(
        self,
        turn: TurnContext,
        phase: PhaseType,
        artifact_type: str,
        payload: dict,
    ) -> None:
        if turn.record.state.scope is None:
            return
        artifact = RuntimeArtifact(
            artifact_type=artifact_type,
            phase=phase.value,
            payload=payload,
        )
        ref = await turn.repository.save_runtime_artifact(turn.record.state.scope, artifact)
        refs = turn.record.state.phase_artifact_refs.setdefault(phase.value, [])
        refs.append(ref)
        refs[:] = refs[-6:]


class BasePhaseRunner:
    phase: PhaseType

    def __init__(self, emitter: StreamEmitter, artifacts: PhaseArtifactStore) -> None:
        self.emitter = emitter
        self.artifacts = artifacts

    # --- 아래 메서드 이름은 "(이 러너가) 무엇을 한다"로 읽히게 지었다 ---

    def stop_if_cancelled(self, turn: TurnContext) -> None:
        """(러너가) 취소됐으면 라운드를 중단한다.

        CancelledTurn 을 던지면 상위 워크플로가 받아 "취소됨" 안내로 마무리한다.
        라운드 중간중간에서 불러, 취소가 빨리 반영되게 한다.
        """
        if turn.record.cancelled:
            raise CancelledTurn

    def enter_phase(self, turn: TurnContext) -> None:
        """(러너가) 이 단계로 진입했음을 상태에 표시한다."""
        turn.record.state.current_phase = self.phase

    def load_analysis_signals(self, turn: TurnContext) -> list[Signal]:
        """(러너가) 앞선 분석 단계가 남긴 신호를 불러온다."""
        return self._load_saved(turn, PhaseType.DATA_ANALYSIS, "signals", Signal)

    def load_drafted_hypotheses(self, turn: TurnContext) -> list[Hypothesis]:
        """(러너가) 앞선 가설 단계가 남긴 가설을 불러온다."""
        return self._load_saved(turn, PhaseType.HYPOTHESIS_GEN, "hypotheses", Hypothesis)

    def _load_saved(self, turn: TurnContext, phase: PhaseType, key: str, model):
        """[내부 도구] 저장해 둔 결과물을 모델 객체로 되살린다 (위 두 로더가 사용)."""
        raw_items = turn.record.state.phase_artifacts[phase.value].get(key, [])
        return [model(**raw) for raw in raw_items]

    async def _save_round_result(
        self,
        turn: TurnContext,
        *,
        key: str,
        payload,
        progress_id: str,
        saving_title: str,
        saved_title: str,
        detail: str,
    ) -> None:
        """결과물을 (1) 대화 상태와 (2) 저장소 양쪽에 보관하고 진행 상황을 알린다.

        세 라운드(분석/가설/계획)가 똑같이 반복하던 '저장 안무'를 한곳에 모았다.
        진행 문구(saving_title 등)는 프런트가 문자열로 매칭하므로 호출부가 그대로
        넘긴다.
        """
        turn.record.state.phase_artifacts[self.phase.value][key] = payload
        await self.emitter.progress(turn.record, progress_id, saving_title, "running", detail)
        await self.artifacts.save(turn, self.phase, key, {key: payload})
        await self.emitter.progress(turn.record, progress_id, saved_title, "done", detail)
