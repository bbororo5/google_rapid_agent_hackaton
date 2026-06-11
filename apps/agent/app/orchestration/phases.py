"""Declarative phase runners for round-based agent work."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Protocol

from pydantic import ValidationError

from app import tracing
from app.agents import formatter, reviewer, workers
from app.contracts import DateRange, Hypothesis, Signal
from app.ids import approval_id
from app.orchestration.emitter import StreamEmitter
from app.orchestration.models import CancelledTurn, TurnContext, TurnOutcome
from app.runtime import blocks
from app.runtime.episode_query import recent_episode_context
from app.runtime.repository import RuntimeArtifact
from app.runtime.state import PhaseType

log = logging.getLogger("launchpilot.orchestration.phases")


class PhaseRunner(Protocol):
    phase: PhaseType

    async def run(self, turn: TurnContext) -> TurnOutcome:
        ...


class PhaseArtifactStore:
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

    def check_cancelled(self, turn: TurnContext) -> None:
        if turn.record.cancelled:
            raise CancelledTurn


class AnalysisRoundRunner(BasePhaseRunner):
    phase = PhaseType.DATA_ANALYSIS

    async def run(self, turn: TurnContext) -> TurnOutcome:
        self.check_cancelled(turn)
        date_range = analysis_window()
        turn.record.state.current_phase = self.phase
        await self.emitter.assistant_text(
            turn.record,
            "Comparing the campaign metrics against the recent baseline to find signals.",
        )
        log.info("[analysis] analyst start (llm=gemini)")
        await self.emitter.progress(
            turn.record,
            "analysis.prepare",
            "Preparing analysis window",
            "done",
            f"{date_range.start}..{date_range.end}",
        )
        await self.emitter.progress(
            turn.record,
            "analysis.evidence",
            "Checking metric baseline and campaign evidence",
            "running",
        )
        memory_context = await recent_episode_context(
            turn.repository, turn.record.state.scope, self.phase
        )
        # A backtrack to a weak metric can yield zero signals; the analyst output
        # then fails the >=1 contract. Treat that as a graceful "no signals"
        # round, not a thread crash, so backtracks stay coherent (ADR-005 R2/R3).
        try:
            async with self.emitter.activity(
                turn.record,
                "analysis.draft",
                "Drafting signal analysis with Gemini",
                "Drafted signal analysis",
            ):
                signal_out = await workers.run_analyst(turn.content, date_range, memory_context)
            signals: list[Signal] = signal_out.signals
        except ValidationError:
            signals = []
        if not signals:
            await self.emitter.assistant_text(
                turn.record,
                "I did not find a strong signal with this criterion. Try a different metric or date range.",
            )
            return TurnOutcome({"phase": self.phase.value, "signals": 0, "status": "no_signals"})
        signal_payload = [sig.model_dump(mode="json") for sig in signals]
        turn.record.state.phase_artifacts[self.phase.value]["signals"] = signal_payload
        await self.emitter.progress(
            turn.record,
            "artifact.save.analysis",
            "Saving analysis artifacts",
            "running",
            f"{len(signals)} signal(s)",
        )
        await self.artifacts.save(turn, self.phase, "signals", {"signals": signal_payload})
        await self.emitter.progress(
            turn.record,
            "artifact.save.analysis",
            "Saved analysis artifacts",
            "done",
            f"{len(signals)} signal(s)",
        )
        log.info("[analysis] analyst done: %d signal(s)", len(signals))
        await self.emitter.progress(
            turn.record,
            "analysis.evidence",
            "Checked metric baseline and campaign evidence",
            "done",
        )
        for sig in signals:
            await self.emitter.assistant_blocks(
                turn.record,
                [
                    blocks.text_block(sig.description),
                    blocks.artifact_block(sig.id, "signal", sig.title, sig.model_dump(mode="json")),
                ],
            )
        await self.emitter.assistant_text(
            turn.record,
            "Analysis is complete. You can use these signals to generate hypotheses next.",
        )
        return TurnOutcome({"phase": self.phase.value, "signals": len(signals)})


class HypothesisRoundRunner(BasePhaseRunner):
    phase = PhaseType.HYPOTHESIS_GEN

    async def run(self, turn: TurnContext) -> TurnOutcome:
        self.check_cancelled(turn)
        turn.record.state.current_phase = self.phase
        signals = [
            Signal(**raw)
            for raw in turn.record.state.phase_artifacts[PhaseType.DATA_ANALYSIS.value].get("signals", [])
        ]
        if not signals:
            await self.emitter.system_error(
                turn.record,
                "Analysis required",
                "Run the data analysis round before generating hypotheses.",
            )
            return TurnOutcome({"phase": self.phase.value, "status": "missing_analysis"})

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
        hypotheses: list[Hypothesis] = hyp_out.hypotheses
        hypothesis_payload = [hyp.model_dump(mode="json") for hyp in hypotheses]
        turn.record.state.phase_artifacts[self.phase.value]["hypotheses"] = hypothesis_payload
        await self.emitter.progress(
            turn.record,
            "artifact.save.hypothesis",
            "Saving hypothesis artifacts",
            "running",
            f"{len(hypotheses)} hypothesis(es)",
        )
        await self.artifacts.save(turn, self.phase, "hypotheses", {"hypotheses": hypothesis_payload})
        await self.emitter.progress(
            turn.record,
            "artifact.save.hypothesis",
            "Saved hypothesis artifacts",
            "done",
            f"{len(hypotheses)} hypothesis(es)",
        )
        log.info("[hypothesis] strategist done: %d hypothesis(es)", len(hypotheses))
        await self.emitter.progress(turn.record, "hypothesis.evidence", "Checked team context", "done")
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
            "Hypotheses are ready. Choose one when you want to turn it into an experiment plan.",
        )
        return TurnOutcome({"phase": self.phase.value, "hypotheses": len(hypotheses)})


class PlanRoundRunner(BasePhaseRunner):
    phase = PhaseType.EXPERIMENT_PLAN

    async def run(self, turn: TurnContext) -> TurnOutcome:
        self.check_cancelled(turn)
        date_range = analysis_window()
        turn.record.state.current_phase = self.phase
        signals = [
            Signal(**raw)
            for raw in turn.record.state.phase_artifacts[PhaseType.DATA_ANALYSIS.value].get("signals", [])
        ]
        hypotheses = [
            Hypothesis(**raw)
            for raw in turn.record.state.phase_artifacts[PhaseType.HYPOTHESIS_GEN.value].get("hypotheses", [])
        ]
        if not signals or not hypotheses:
            await self.emitter.system_error(
                turn.record,
                "Hypotheses required",
                "Complete the analysis and hypothesis rounds before drafting an experiment plan.",
            )
            return TurnOutcome({"phase": self.phase.value, "status": "missing_hypotheses"})

        log.info("[plan] writer start")
        await self.emitter.progress(
            turn.record,
            "plan.load_context",
            "Loaded signals and hypotheses for planning",
            "done",
            f"{len(signals)} signal(s), {len(hypotheses)} hypothesis(es)",
        )
        memory_context = await recent_episode_context(
            turn.repository, turn.record.state.scope, self.phase
        )
        async with self.emitter.activity(
            turn.record,
            "plan.draft",
            "Drafting experiment plan with Gemini",
            "Drafted experiment plan",
        ):
            plan = (
                await workers.run_writer(turn.content, date_range, hypotheses, memory_context)
            ).experiment_plan
        plan_payload = plan.model_dump(mode="json")
        turn.record.state.phase_artifacts[self.phase.value]["experiment_plan"] = plan_payload
        turn.record.state.active_artifact_id = plan.id
        await self.emitter.progress(
            turn.record,
            "artifact.save.plan",
            "Saving experiment plan artifact",
            "running",
            plan.id,
        )
        await self.artifacts.save(turn, self.phase, "experiment_plan", {"experiment_plan": plan_payload})
        await self.emitter.progress(
            turn.record,
            "artifact.save.plan",
            "Saved experiment plan artifact",
            "done",
            plan.id,
        )
        log.info("[plan] writer done: %d item(s)", len(plan.items))

        payload = formatter.assemble(signals, hypotheses, plan)
        await self.emitter.progress(turn.record, "plan.review", "Checking approval guardrails", "running")
        gmeta = {
            "thread_id": turn.record.thread_id,
            "workspace_id": turn.record.workspace_id,
            "campaign_id": turn.record.campaign_id,
        }
        with tracing.guardrail_span(
            "launchpilot.reviewer_gate",
            input_value={"signals": len(signals), "hypotheses": len(hypotheses), "items": len(plan.items)},
            metadata={**gmeta, "validator_passed": None, "backtrack_count": 0},
            workspace_id=turn.record.workspace_id,
            campaign_id=turn.record.campaign_id,
        ) as g_span:
            report = reviewer.review(payload)
            tracing.set_output(g_span, report.model_dump(mode="json"))
            tracing.set_metadata(g_span, {**gmeta, "validator_passed": report.passed, "backtrack_count": 0})
        log.info("[plan] reviewer passed=%s issues=%d", report.passed, len(report.issues))
        if not report.passed:
            await self.emitter.progress(
                turn.record,
                "plan.review",
                "Approval guardrails failed",
                "failed",
                f"{len(report.issues)} issue(s)",
            )
            await self.emitter.system_error(
                turn.record,
                "Validation failed",
                "; ".join(issue.message for issue in report.issues),
            )
            return TurnOutcome({"phase": self.phase.value, "validator_passed": False})
        await self.emitter.progress(turn.record, "plan.review", "Approval guardrails passed", "done")

        pending_approval_id = approval_id()
        turn.record.state.pending_approval_id = pending_approval_id
        await self.emitter.assistant_blocks(
            turn.record,
            [
                blocks.text_block("The experiment plan draft is ready. Please review and approve."),
                blocks.artifact_block(plan.id, "experiment_plan", plan.summary, plan_payload),
            ],
        )
        await self.emitter.assistant_blocks(
            turn.record,
            [blocks.approval_block(pending_approval_id, "Approve experiment plan", plan.id, payload.model_dump(mode="json"))],
        )
        log.info("plan round done thread=%s approval emitted plan=%s", turn.record.thread_id, plan.id)
        return TurnOutcome(
            {
                "phase": self.phase.value,
                "plan_id": plan.id,
                "experiments": len(plan.items),
                "validator_passed": True,
            }
        )


class UnsupportedPhaseRunner(BasePhaseRunner):
    phase = PhaseType.EXPERIMENT_EVAL

    async def run(self, turn: TurnContext) -> TurnOutcome:
        await self.emitter.assistant_text(
            turn.record,
            "Experiment evaluation is handled after run results are available in a later analysis round.",
        )
        return TurnOutcome({"mode": "phase_not_implemented", "phase": self.phase.value})


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


def analysis_window() -> DateRange:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=6)
    return DateRange(start=start.isoformat(), end=end.isoformat())


def baseline_window(current: DateRange) -> DateRange:
    cur_start = date.fromisoformat(current.start)
    return DateRange(
        start=(cur_start - timedelta(days=28)).isoformat(),
        end=(cur_start - timedelta(days=1)).isoformat(),
    )
