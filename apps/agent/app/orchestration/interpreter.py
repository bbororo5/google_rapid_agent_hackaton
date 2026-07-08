"""LLM turn interpretation as an object with explicit overrides."""

from __future__ import annotations

import asyncio

from app.agents import workers
from app.orchestration.context import PromptContextBuilder
from app.orchestration.emitter import StreamEmitter
from app.orchestration.models import TurnContext, TurnDecision
from app.runtime.state import (
    TurnIntent,
    PhaseType,
    ResponseMode,
    decide_delegation,
    apply_proposed_change,
)


class TurnInterpreter:
    def __init__(self, emitter: StreamEmitter, prompts: PromptContextBuilder) -> None:
        self._emitter = emitter
        self._prompts = prompts

    async def interpret(self, turn: TurnContext) -> TurnDecision:
        await self._emitter.progress(
            turn.record,
            "turn.interpret",
            "사용자 요청 해석 중",
            "running",
        )
        prompt_context = self._prompts.build_interpreter_context(turn)
        has_csv = self._has_attachment_kind(turn.attachments, "csv_import")
        content_for_interpreter = turn.content
        if has_csv:
            # 첨부 사실을 해석기에 알리되, 의도 분류는 사용자 문장에 맡긴다.
            # "저장해줘"는 CHAT으로, "분석해줘"는 START_ANALYSIS로 갈라져야 한다.
            content_for_interpreter = (
                f"{turn.content}\n\n[attachment] campaign metrics CSV file "
                "(already ingested into the evidence store by the backend)"
            )
        delta = await workers.run_turn_interpreter(
            content_for_interpreter,
            prompt_context,
            turn.record.state.current_phase,
        )
        if has_csv:
            delta.mutation["has_csv_attachment"] = True
            # 텍스트 없이 CSV만 던진 턴은 기존 원클릭 분석 흐름을 유지한다.
            if not turn.content.strip():
                delta.intent = TurnIntent.START_ANALYSIS
            # 분석 의도로 판정된 경우에만 라운드 실행을 확정한다.
            if delta.intent == TurnIntent.START_ANALYSIS:
                delta.response_mode = ResponseMode.RERUN
                delta.target_phase = PhaseType.DATA_ANALYSIS
                delta.restart_from_phase = PhaseType.DATA_ANALYSIS
        await self._emitter.progress(
            turn.record,
            "turn.interpret",
            "사용자 요청 해석 완료",
            "done",
            f"{delta.intent.value} / {delta.response_mode.value}",
        )

        await self._emitter.progress(
            turn.record,
            "state.reduce",
            "워크플로 가드레일 적용 중",
            "running",
        )
        # 스레드로 내린다: START_ANALYSIS 가드가 저장 데이터 확인차 동기 ES 조회를
        # 할 수 있어서, 이벤트 루프를 막지 않게 한다.
        reducer = await asyncio.to_thread(
            apply_proposed_change, turn.record.state, delta, turn.content
        )
        delegation = decide_delegation(reducer)
        await self._emitter.progress(
            turn.record,
            "state.reduce",
            "워크플로 가드레일 적용 완료",
            "done",
            f"{reducer.decision.value} -> {delegation.mode.value}",
        )
        return TurnDecision(delta=delta, reducer=reducer, delegation=delegation)

    def _has_attachment_kind(self, attachments: tuple, kind: str) -> bool:
        for attachment in attachments:
            if getattr(attachment, "kind", None) == kind:
                return True
            if isinstance(attachment, dict) and attachment.get("kind") == kind:
                return True
        return False
