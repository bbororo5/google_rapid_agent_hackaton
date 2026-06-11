"""Declarative object graph for processing one conversation turn."""

from __future__ import annotations

import logging

from app import tracing
from app.orchestration.committer import StateCommitter
from app.orchestration.context import PromptContextBuilder, TurnContextLoader
from app.orchestration.emitter import StreamEmitter
from app.orchestration.interpreter import TurnInterpreter
from app.orchestration.models import CancelledTurn
from app.orchestration.phases import PhaseRunnerRegistry
from app.orchestration.router import TurnRouter
from app.runtime.thread_store import ThreadRecord

log = logging.getLogger("launchpilot.orchestration.workflow")


class TurnWorkflow:
    """Coordinates declarative turn components without owning their details."""

    def __init__(self) -> None:
        self.emitter = StreamEmitter()
        prompts = PromptContextBuilder()
        phases = PhaseRunnerRegistry(self.emitter)
        self.loader = TurnContextLoader(self.emitter)
        self.interpreter = TurnInterpreter(self.emitter, prompts)
        self.router = TurnRouter(self.emitter, phases)
        self.committer = StateCommitter(self.emitter)

    async def run(self, record: ThreadRecord, content: str, attachments: tuple = ()) -> None:
        turn = await self.loader.load(record, content, attachments)
        with tracing.agent_span(
            "launchpilot.thread",
            input_value=content[:2000],
            metadata=turn.trace_metadata,
            workspace_id=record.workspace_id,
            campaign_id=record.campaign_id,
        ) as turn_span:
            try:
                decision = await self.interpreter.interpret(turn)
                log.info(
                    "turn thread=%s intent=%s phase=%s target=%s has_scope=%s content=%r",
                    record.thread_id,
                    decision.delta.intent.value,
                    record.state.current_phase.value,
                    record.state.target_phase.value,
                    turn.has_scope,
                    content[:80],
                )
                tracing.set_metadata(
                    turn_span,
                    {
                        **turn.trace_metadata,
                        "agent.scope.workspace_id": record.workspace_id,
                        "agent.scope.campaign_id": record.campaign_id,
                        "agent.repository.backend": turn.repository.backend_name,
                        **decision.trace_metadata,
                    },
                )
                outcome = await self.router.route(turn, decision)
                tracing.set_output(turn_span, outcome.trace_output)
                if outcome.commit_state:
                    await self.committer.commit(turn, decision, turn_span)
            except CancelledTurn:
                log.info("turn cancelled thread=%s", record.thread_id)
                await self.emitter.system_result(record, "Run cancelled", "The analysis was cancelled.")
            except Exception as exc:  # noqa: BLE001 - user-safe error boundary
                log.exception("turn failed thread=%s", record.thread_id)
                await self.emitter.system_error(record, "Agent error", f"{type(exc).__name__}: {exc}")
