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
    """Raised internally when a cancel was requested between stages."""


def _check_cancel(record: RunRecord) -> None:
    # Best-effort cancellation: we only honor it at stage boundaries, not mid-LLM.
    if record.cancelled:
        raise _Cancelled


def _log_tool(record: RunRecord, tool_name: str) -> None:
    # Append a tool-call log line (surfaced in the GET snapshot for diagnostics).
    record.tool_call_logs.append(
        ToolCallLog(
            sequence=len(record.tool_call_logs) + 1,
            tool_name=tool_name,
            status=ToolCallStatus.SUCCESS,
            duration_ms=5,
        )
    )


async def execute(record: RunRecord) -> None:
    """Run the full pipeline for a run. Safe to launch as a background task.

    Wraps _run so any failure becomes a contract event rather than an unhandled
    task exception: a requested cancel -> run.cancelled, anything else -> run.failed.
    """
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

    # Pre-injection (Orchestrator-owned). Continuity isn't implemented yet, so
    # parent_brief load is a no-op; we only record whether reflection is wired.
    record.phoenix_reflection_used = bool(settings.phoenix_endpoint)

    # --- Stage 1: Analyst (detect signals, then ground them) ---
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
    # Emit one glass-box card per signal so the UI can show progress live.
    for sig in signals:
        await emitter.observation(
            record,
            kind=AgentObservationKind.signal,
            title=sig.title,
            summary=sig.description,
            evidence_refs=sig.evidence_refs,
        )
    # Grounding is part of the analyst's tool use; mark the evidence sub-stage done.
    await emitter.step_updated(
        record,
        order=1,
        stage=AgentRunStage.GROUND_WITH_EVIDENCE,
        status=AgentStepStatus.SUCCEEDED,
        run_status=AgentRunStatus.RUNNING_EVIDENCE_SEARCH,
    )
    await emitter.signal_detected(record, payload=None)  # milestone marker

    # --- Stage 2: Strategist (why hypotheses) ---
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

    # --- Stage 3: Writer (experiment plan) ---
    _check_cancel(record)
    await emitter.step_updated(
        record,
        order=3,
        stage=AgentRunStage.DRAFT_EXPERIMENT_PLAN,
        status=AgentStepStatus.IN_PROGRESS,
        run_status=AgentRunStatus.RUNNING_EXPERIMENT_GENERATION,
    )
    plan = (await workers.run_writer(req, hypotheses)).experiment_plan

    # --- Stage 4: Reviewer gate + prefix-reuse backtracking ---
    # Assemble -> review. On fail, regenerate only from the root-cause worker and
    # downstream (the successful prefix is reused), up to the backtrack limit.
    while True:
        _check_cancel(record)
        payload = formatter.assemble(signals, hypotheses, plan)
        report = reviewer.review(payload)
        record.validator_passed = report.passed
        if report.passed:
            record.payload = payload
            break
        if record.backtrack_count >= settings.backtrack_limit:
            # Out of retries -> terminal failure (loop guard, P4).
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
        # Regenerate from the root cause downstream; earlier good artifacts stay.
        if target in ("analyst", "generator"):
            signals = (await workers.run_analyst(req)).signals
            hypotheses = (await workers.run_strategist(req, signals)).hypotheses
            plan = (await workers.run_writer(req, hypotheses)).experiment_plan
        elif target == "strategist":
            hypotheses = (await workers.run_strategist(req, signals)).hypotheses
            plan = (await workers.run_writer(req, hypotheses)).experiment_plan
        else:  # writer / formatter
            plan = (await workers.run_writer(req, hypotheses)).experiment_plan

    # --- Done: open the approval gate (Java takes over from here) ---
    await emitter.step_updated(
        record,
        order=4,
        stage=AgentRunStage.WAIT_FOR_APPROVAL,
        status=AgentStepStatus.SUCCEEDED,
        run_status=AgentRunStatus.WAITING_FOR_APPROVAL,
    )
    await emitter.experiment_plan_drafted(record, payload=record.payload)
