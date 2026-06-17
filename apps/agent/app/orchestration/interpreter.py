"""LLM turn interpretation as an object with explicit overrides."""

from __future__ import annotations

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
            "Interpreting user request",
            "running",
        )
        prompt_context = self._prompts.build_interpreter_context(turn)
        delta = await workers.run_turn_interpreter(
            turn.content,
            prompt_context,
            turn.record.state.current_phase,
        )
        if self._has_attachment_kind(turn.attachments, "csv_import"):
            delta.intent = TurnIntent.START_ANALYSIS
            delta.response_mode = ResponseMode.RERUN
            delta.target_phase = PhaseType.DATA_ANALYSIS
            delta.restart_from_phase = PhaseType.DATA_ANALYSIS
            delta.mutation["has_csv_attachment"] = True
        await self._emitter.progress(
            turn.record,
            "turn.interpret",
            "Interpreted user request",
            "done",
            f"{delta.intent.value} / {delta.response_mode.value}",
        )

        await self._emitter.progress(
            turn.record,
            "state.reduce",
            "Applying workflow guardrails",
            "running",
        )
        reducer = apply_proposed_change(turn.record.state, delta, turn.content)
        delegation = decide_delegation(reducer)
        await self._emitter.progress(
            turn.record,
            "state.reduce",
            "Applied workflow guardrails",
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
