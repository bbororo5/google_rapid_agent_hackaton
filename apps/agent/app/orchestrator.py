"""Golden-path orchestrator (mode M3: fixed 4 workers).

Sequence: analyst -> strategist -> writer -> reviewer, with deterministic review
and prefix-reuse backtracking on fail (agent-tool-spec §4). Question-based
routing (M1/M2) is intentionally deferred; this always runs the full pipeline.

Emits contract-02 workflow events at each stage. Cancellation is checked between
stages (best-effort).
"""
from __future__ import annotations

from app.agents import failure, formatter, reviewer, workers
from app.config import get_settings
from app.contracts import (
    AgentObservationKind,
    AgentResultPayload,
    AgentRunStage,
    AgentRunStatus,
    AgentStepStatus,
    Hypothesis,
    Signal,
    ToolCallLog,
    ToolCallStatus,
)
from app.runtime import emitter
from app.runtime.store import RunRecord


class _Cancelled(Exception):
    pass


def _check_cancel(record: RunRecord) -> None:
    if record.cancelled:
        raise _Cancelled


def _log_tool(record: RunRecord, tool_name: str) -> None:
    record.tool_call_logs.append(
        ToolCallLog(
            sequence=len(record.tool_call_logs) + 1,
            tool_name=tool_name,
            status=ToolCallStatus.SUCCESS,
            duration_ms=5,
        )
    )


async def execute(record: RunRecord) -> None:
    """Run the full pipeline for a run. Safe to launch as a background task."""
    try:
        await _run(record)
    except _Cancelled:
        await emitter.run_cancelled(record)
    except Exception as exc:  # noqa: BLE001 - any worker/LLM failure terminates the run
        await emitter.run_failed(record, f"{type(exc).__name__}: {exc}")


async def _run(record: RunRecord) -> None:
    req = record.request
    settings = get_settings()
    await emitter.run_started(record)

    # Pre-injection (Orchestrator-owned). Continuity not implemented -> no-op.
    record.phoenix_reflection_used = bool(settings.phoenix_endpoint)

    # --- Analyst: detect signals + ground ---
    _check_cancel(record)
    await emitter.step_updated(
        record,
        order=1,
        stage=AgentRunStage.DETECT_PERFORMANCE_SIGNAL,
        status=AgentStepStatus.IN_PROGRESS,
        run_status=AgentRunStatus.RUNNING_SIGNAL_DETECTION,
    )
    signal_out = await workers.run_analyst(req)
    signals: list[Signal] = signal_out.signals
    _log_tool(record, "query_metric_baseline")
    _log_tool(record, "search_content_posts")
    for sig in signals:
        await emitter.observation(
            record,
            kind=AgentObservationKind.signal,
            title=sig.title,
            summary=sig.description,
            evidence_refs=sig.evidence_refs,
        )
    await emitter.step_updated(
        record,
        order=1,
        stage=AgentRunStage.GROUND_WITH_EVIDENCE,
        status=AgentStepStatus.SUCCEEDED,
        run_status=AgentRunStatus.RUNNING_EVIDENCE_SEARCH,
    )
    await emitter.signal_detected(record, payload=None)

    # --- Strategist: hypotheses ---
    _check_cancel(record)
    await emitter.step_updated(
        record,
        order=2,
        stage=AgentRunStage.GENERATE_HYPOTHESIS,
        status=AgentStepStatus.IN_PROGRESS,
        run_status=AgentRunStatus.RUNNING_HYPOTHESIS_GENERATION,
    )
    hyp_out = await workers.run_strategist(req, signals)
    hypotheses: list[Hypothesis] = hyp_out.hypotheses
    _log_tool(record, "search_team_notes")
    for hyp in hypotheses:
        await emitter.observation(
            record,
            kind=AgentObservationKind.hypothesis,
            title=hyp.statement,
            summary=hyp.rationale,
            evidence_refs=hyp.supporting_evidence_refs,
        )
    await emitter.hypothesis_created(record, payload=None)

    # --- Writer: experiment plan ---
    _check_cancel(record)
    await emitter.step_updated(
        record,
        order=3,
        stage=AgentRunStage.DRAFT_EXPERIMENT_PLAN,
        status=AgentStepStatus.IN_PROGRESS,
        run_status=AgentRunStatus.RUNNING_EXPERIMENT_GENERATION,
    )
    plan = (await workers.run_writer(req, hypotheses)).experiment_plan

    # --- Reviewer gate + prefix-reuse backtracking ---
    while True:
        _check_cancel(record)
        payload = formatter.assemble(signals, hypotheses, plan)
        report = reviewer.review(payload)
        record.validator_passed = report.passed
        if report.passed:
            record.payload = payload
            break
        if record.backtrack_count >= settings.backtrack_limit:
            await emitter.run_failed(
                record, f"validation failed after {record.backtrack_count} backtracks"
            )
            return
        record.backtrack_count += 1
        target = failure.route([i.code for i in report.issues])
        await emitter.observation(
            record,
            kind=AgentObservationKind.warning,
            title=f"Validation failed -> re-running {target}",
            summary=report.retry_instruction or "",
        )
        # Prefix reuse: only regenerate from the root-cause worker downstream.
        if target in ("analyst", "generator"):
            signals = (await workers.run_analyst(req)).signals
            hypotheses = (await workers.run_strategist(req, signals)).hypotheses
            plan = (await workers.run_writer(req, hypotheses)).experiment_plan
        elif target == "strategist":
            hypotheses = (await workers.run_strategist(req, signals)).hypotheses
            plan = (await workers.run_writer(req, hypotheses)).experiment_plan
        else:  # writer / formatter
            plan = (await workers.run_writer(req, hypotheses)).experiment_plan

    # --- Approval gate ---
    await emitter.step_updated(
        record,
        order=4,
        stage=AgentRunStage.WAIT_FOR_APPROVAL,
        status=AgentStepStatus.SUCCEEDED,
        run_status=AgentRunStatus.WAITING_FOR_APPROVAL,
    )
    await emitter.experiment_plan_drafted(record, payload=record.payload)
