"""분석 라운드: 캠페인 지표에서 두드러진 신호를 찾는다."""
from __future__ import annotations

from pydantic import ValidationError

from app.agents import workers
from app.contracts import Signal
from app.orchestration.models import TurnContext, TurnOutcome
from app.orchestration.phases.base import BasePhaseRunner, log
from app.orchestration.phases.windows import analysis_window
from app.runtime import blocks
from app.runtime.episode_query import recent_episode_context
from app.runtime.state import PhaseType


class AnalysisRoundRunner(BasePhaseRunner):
    """분석 라운드: 캠페인 지표에서 두드러진 신호를 찾는다."""

    phase = PhaseType.DATA_ANALYSIS

    async def run(self, turn: TurnContext) -> TurnOutcome:
        # 목표: 캠페인 지표에서 두드러진 신호를 찾아 사용자에게 제시한다.
        #       신호가 하나도 없으면 다른 기준을 제안하며 끝낸다.
        self.stop_if_cancelled(turn)               # 취소됐으면 중단한다
        self.enter_phase(turn)                     # 분석 단계로 진입한다
        await self._announce_start(turn)           # 시작을 알린다
        signals = await self._detect_signals(turn)  # 신호를 찾는다
        if not signals:
            return await self._report_no_signals(turn)  # 없으면 안내하고 끝낸다
        await self._save_signals(turn, signals)    # 신호를 저장한다
        await self._show_signals(turn, signals)    # 신호를 제시한다
        return TurnOutcome({"phase": self.phase.value, "signals": len(signals)})

    async def _announce_start(self, turn: TurnContext) -> None:
        # 무엇을 할지 사용자에게 알리고, 분석 기간을 준비 완료로 표시한다.
        await self.emitter.assistant_text(
            turn.record,
            "Comparing the campaign metrics against the recent baseline to find signals.",
        )
        log.info("[analysis] analyst start (llm=gemini)")
        date_range = analysis_window()
        await self.emitter.progress(
            turn.record,
            "analysis.prepare",
            "Preparing analysis window",
            "done",
            f"{date_range.start}..{date_range.end}",
        )

    async def _detect_signals(self, turn: TurnContext) -> list[Signal]:
        # 분석가(Gemini)를 불러 신호를 뽑는다.
        # 되돌리기 후 약한 지표를 보면 신호가 0개일 수 있는데, 그때 분석가 출력은
        # ">=1개" 계약을 어겨 ValidationError가 난다. 이건 스레드 크래시가 아니라
        # "신호 없음" 라운드로 부드럽게 처리한다 (ADR-005 R2/R3).
        await self.emitter.progress(
            turn.record,
            "analysis.evidence",
            "Checking metric baseline and campaign evidence",
            "running",
        )
        memory_context = await recent_episode_context(
            turn.repository, turn.record.state.scope, self.phase
        )
        try:
            async with self.emitter.activity(
                turn.record,
                "analysis.draft",
                "Drafting signal analysis with Gemini",
                "Drafted signal analysis",
            ):
                signal_out = await workers.run_analyst(turn.content, analysis_window(), memory_context)
            return signal_out.signals
        except ValidationError:
            return []

    async def _report_no_signals(self, turn: TurnContext) -> TurnOutcome:
        # 신호가 없으면 다른 기준을 제안하며 라운드를 깔끔히 끝낸다.
        await self.emitter.assistant_text(
            turn.record,
            "이 기준으로는 두드러진 신호를 찾지 못했어요. 다른 지표나 기간으로 다시 분석해볼까요?",
        )
        return TurnOutcome({"phase": self.phase.value, "signals": 0, "status": "no_signals"})

    async def _save_signals(self, turn: TurnContext, signals: list[Signal]) -> None:
        # 신호를 상태 + 저장소에 보관하고(공통 헬퍼), 근거 확인 완료를 알린다.
        signal_payload = [signal.model_dump(mode="json") for signal in signals]
        await self._save_round_result(
            turn,
            key="signals",
            payload=signal_payload,
            progress_id="artifact.save.analysis",
            saving_title="Saving analysis artifacts",
            saved_title="Saved analysis artifacts",
            detail=f"{len(signals)} signal(s)",
        )
        log.info("[analysis] analyst done: %d signal(s)", len(signals))
        await self.emitter.progress(
            turn.record,
            "analysis.evidence",
            "Checked metric baseline and campaign evidence",
            "done",
        )

    async def _show_signals(self, turn: TurnContext, signals: list[Signal]) -> None:
        # 신호 하나하나를 설명 + 아티팩트 블록으로 화면에 흘려보낸다.
        for signal in signals:
            await self.emitter.assistant_blocks(
                turn.record,
                [
                    blocks.text_block(signal.description),
                    blocks.artifact_block(
                        signal.id, "signal", signal.title, signal.model_dump(mode="json")
                    ),
                ],
            )
        await self.emitter.assistant_text(
            turn.record,
            "분석 결과를 확인했습니다. 원하면 이 신호를 바탕으로 가설을 세울 수 있습니다.",
        )
