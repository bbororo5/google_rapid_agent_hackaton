"""Declarative object graph for processing one conversation turn."""

from __future__ import annotations

import logging

from app import telemetry
from app.orchestration.checkpoint import Checkpointer
from app.orchestration.committer import StateCommitter
from app.orchestration.context import PromptContextBuilder, TurnContextLoader
from app.orchestration.emitter import StreamEmitter
from app.orchestration.goals import GoalController
from app.orchestration.interpreter import TurnInterpreter
from app.orchestration.loop import AgentLoop
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
        self.goals = GoalController()
        self.loop = AgentLoop(self.emitter, self.router, prompts)
        self.committer = StateCommitter(self.emitter)
        self.checkpointer = Checkpointer(self.emitter)

    async def run(self, record: ThreadRecord, content: str, attachments: tuple = ()) -> None:
        turn = await self.loader.load(record, content, attachments)
        with telemetry.turn_span(
            content,
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
                goal = self.goals.create(turn, decision)
                telemetry.record_turn_decision(
                    turn_span,
                    turn_metadata=turn.trace_metadata,
                    decision_metadata=decision.trace_metadata,
                    workspace_id=record.workspace_id,
                    campaign_id=record.campaign_id,
                    repository_backend=turn.repository.backend_name,
                    goal=goal,
                )
                outcome = await self.loop.run(turn, decision, goal)
                telemetry.record_turn_outcome(turn_span, outcome.trace_output)
                if outcome.commit_state:
                    await self.committer.commit(turn, decision, turn_span)
                    await self.checkpointer.maybe_checkpoint(turn, decision, outcome, turn_span)
            except CancelledTurn:
                log.info("turn cancelled thread=%s", record.thread_id)
                await self.emitter.system_result(record, "Run cancelled", "The analysis was cancelled.")
            except Exception as exc:  # noqa: BLE001 - user-safe error boundary
                log.exception("turn failed thread=%s", record.thread_id)
                await self.emitter.system_error(record, "Agent error", f"{type(exc).__name__}: {exc}")
