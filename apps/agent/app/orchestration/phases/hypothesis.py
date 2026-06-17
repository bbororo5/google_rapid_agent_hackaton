"""가설 라운드: 분석 신호의 원인을 가설로 세운다."""
from __future__ import annotations

from app.agents import workers
from app.contracts import Hypothesis, Signal
from app.orchestration.models import TurnContext, TurnOutcome
from app.orchestration.phases.base import BasePhaseRunner, log
from app.runtime import blocks
from app.runtime.episode_query import recent_episode_context
from app.runtime.state import PhaseType


class HypothesisRoundRunner(BasePhaseRunner):
    """가설 라운드: 분석 신호의 원인을 가설로 세운다."""

    phase = PhaseType.HYPOTHESIS_GEN

    async def run(self, turn: TurnContext) -> TurnOutcome:
        # 목표: 분석 신호로부터 가설을 세워 사용자에게 제시한다.
        #       재료(신호)가 없으면 분석을 먼저 하라고 요청하고 끝낸다.
        self.stop_if_cancelled(turn)                       # 취소됐으면 중단한다
        self.enter_phase(turn)                             # 가설 단계로 진입한다
        signals = self.load_analysis_signals(turn)         # 재료: 앞 단계 신호를 불러온다
        if not signals:
            return await self._require_analysis_first(turn)  # 신호 없으면 분석부터 요청
        hypotheses = await self._generate_hypotheses(turn, signals)  # 가설을 생성한다
        await self._save_hypotheses(turn, hypotheses)               # 가설을 저장한다
        await self._show_hypotheses(turn, hypotheses)               # 가설을 제시한다
        return TurnOutcome({"phase": self.phase.value, "hypotheses": len(hypotheses)})

    async def _require_analysis_first(self, turn: TurnContext) -> TurnOutcome:
        # 신호가 없으면 분석 라운드를 먼저 하라고 안내하고 끝낸다.
        await self.emitter.system_error(
            turn.record,
            "Analysis required",
            "가설을 세우기 전에 먼저 데이터 분석 라운드를 실행해 주세요.",
        )
        return TurnOutcome({"phase": self.phase.value, "status": "missing_analysis"})

    async def _generate_hypotheses(self, turn: TurnContext, signals: list[Signal]) -> list[Hypothesis]:
        # 전략가(Gemini)를 불러 신호로부터 가설을 만든다.
        log.info("[hypothesis] strategist start")
        await self.emitter.progress(
            turn.record,
            "hypothesis.load_signals",
            "Loaded prior signal artifacts",
            "done",
            f"{len(signals)} signal(s)",
        )
        await self.emitter.progress(turn.record, "hypothesis.evidence", "Checking team context", "running")
        memory_context = await recent_episode_context(
            turn.repository, turn.record.state.scope, self.phase
        )
        async with self.emitter.activity(
            turn.record,
            "hypothesis.draft",
            "Drafting hypotheses with Gemini",
            "Drafted hypotheses",
        ):
            hyp_out = await workers.run_strategist(turn.content, signals, memory_context)
        return hyp_out.hypotheses

    async def _save_hypotheses(self, turn: TurnContext, hypotheses: list[Hypothesis]) -> None:
        # 가설을 상태 + 저장소에 보관하고(공통 헬퍼), 팀 컨텍스트 확인 완료를 알린다.
        hypothesis_payload = [hyp.model_dump(mode="json") for hyp in hypotheses]
        await self._save_round_result(
            turn,
            key="hypotheses",
            payload=hypothesis_payload,
            progress_id="artifact.save.hypothesis",
            saving_title="Saving hypothesis artifacts",
            saved_title="Saved hypothesis artifacts",
            detail=f"{len(hypotheses)} hypothesis(es)",
        )
        log.info("[hypothesis] strategist done: %d hypothesis(es)", len(hypotheses))
        await self.emitter.progress(turn.record, "hypothesis.evidence", "Checked team context", "done")

    async def _show_hypotheses(self, turn: TurnContext, hypotheses: list[Hypothesis]) -> None:
        # 가설 하나하나를 근거 + 아티팩트 블록으로 화면에 흘려보낸다.
        for hyp in hypotheses:
            await self.emitter.assistant_blocks(
                turn.record,
                [
                    blocks.text_block(hyp.rationale),
                    blocks.artifact_block(hyp.id, "hypothesis", hyp.statement, hyp.model_dump(mode="json")),
                ],
            )
        await self.emitter.assistant_text(
            turn.record,
            "가설을 정리했습니다. 특정 가설을 선택하면 그때 실험 계획을 세울 수 있습니다.",
        )
