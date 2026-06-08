"""Conversation-first orchestrator (golden path: fixed 4 workers).

A turn drives the work. The first substantive turn on a thread runs the full
analysis pipeline (analyst -> strategist -> writer -> reviewer) and streams
user-safe blocks; later turns get a short free-chat reply. Question-based routing
(per-intent worker selection) is intentionally deferred.

Approve/reject/cancel/revise are resolved in Java and never reach here
(contract 02 README, Action Handling), so this module only ever sees free-form
content turns.

Deterministic review with prefix-reuse backtracking on fail (agent-tool-spec §4).
Cancellation is checked between stages (best-effort).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from app.agents import failure, formatter, reflection, reviewer, workers
from app.tools import evidence
from app.config import get_settings
from app.contracts import (
    AgentResultPayload,
    DateRange,
    Hypothesis,
    Signal,
)
from app.ids import approval_id
from app.runtime import blocks
from app.runtime.thread_store import ThreadRecord
from app import tracing

log = logging.getLogger("launchpilot.orchestrator")


class _Cancelled(Exception):
    """Raised internally when a cancel was requested between stages."""


def _check_cancel(record: ThreadRecord) -> None:
    # Best-effort cancellation: only honored at stage boundaries, not mid-LLM.
    if record.cancelled:
        raise _Cancelled


def _analysis_window() -> DateRange:
    # Synthesize a 7-day analysis window ending today (the turn carries no
    # explicit date range in the conversation-first contract).
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=6)
    return DateRange(start=start.isoformat(), end=end.isoformat())


def _baseline_window(current: DateRange) -> DateRange:
    # Prior ~28 days immediately before the current window (contract 04
    # baseline_window). compute_baseline falls back to a recency split when this
    # window is too sparse, so a short-lived campaign still gets a lift.
    cur_start = date.fromisoformat(current.start)
    return DateRange(
        start=(cur_start - timedelta(days=28)).isoformat(),
        end=(cur_start - timedelta(days=1)).isoformat(),
    )


def _thread_context(record: ThreadRecord, has_csv: bool) -> str:
    # State hint that steers the router/chat reply toward the next concrete step.
    if record.pipeline_started:
        return "analysis_done"
    if has_csv:
        return "ready_to_analyze"
    # No CSV: suggest the upload at most twice, then stay quiet about it.
    return "need_csv" if record.csv_hint_count < 2 else "need_csv_quiet"


async def process_turn(
    record: ThreadRecord, content: str, attachments: tuple = ()
) -> None:
    """Handle one user turn. Safe to launch as a background task.

    Orchestrator routing pass: a single fast router call classifies intent and
    drafts a steering reply. Then either run the analysis pipeline (analysis
    intent + data available) or emit the router's reply. Any failure becomes an
    error block rather than an unhandled task exception.
    """
    has_csv = bool(attachments) or record.workspace_id is not None
    context = _thread_context(record, has_csv)
    # AGENT span: the whole thread turn (contract 06 §Span Hierarchy).
    meta = {
        "thread_id": record.thread_id,
        "workspace_id": record.workspace_id,
        "campaign_id": record.campaign_id,
        "stage": "TURN",
    }
    with tracing.agent_span(
        "launchpilot.thread",
        input_value=content[:2000],
        metadata=meta,
        workspace_id=record.workspace_id,
        campaign_id=record.campaign_id,
    ) as turn_span:
      try:
        route = await workers.run_router(content, context)
        intent = route["intent"]
        log.info("turn thread=%s intent=%s has_csv=%s pipeline_started=%s content=%r",
                 record.thread_id, intent, has_csv, record.pipeline_started, content[:80])
        tracing.set_metadata(turn_span, {**meta, "intent": intent})

        if intent == "analyze":
            # Analysis no longer requires a fresh CSV: with no upload we analyze
            # the existing baseline data; with an upload we factor it in too.
            # Re-runnable: a later "analyze" (e.g. after a mid-thread CSV upload)
            # starts a fresh pass over the now-updated data.
            record.pipeline_started = True
            # Scope every evidence query in this run to the turn's campaign +
            # analysis window (read from the ContextVar by the evidence tools).
            current = _analysis_window()
            baseline = _baseline_window(current)
            # CHAIN span: the orchestrator pipeline (analyst..reviewer). Parents
            # the worker LLM/tool spans and the reviewer gate inside.
            with evidence.scope(
                record.workspace_id, record.campaign_id,
                current.start, current.end, baseline.start, baseline.end,
            ), tracing.chain_span(
                "launchpilot.orchestrator",
                input_value=content[:2000],
                metadata={**meta, "stage": "PIPELINE"},
                workspace_id=record.workspace_id,
                campaign_id=record.campaign_id,
            ):
                await _run_pipeline(record, content)
        else:
            # chat, or analysis already done -> emit the router's reply. The CSV
            # nudge lives in the router context (need_csv -> need_csv_quiet after
            # two turns) so the reply stays in the user's own language.
            if context == "need_csv":
                record.csv_hint_count += 1
            reply = route.get("reply") or "How can I help with your campaign analysis?"
            log.info("chat reply thread=%s context=%s hint=%d", record.thread_id, context, record.csv_hint_count)
            await blocks.assistant(record, [blocks.text_block(reply)])
      except _Cancelled:
        log.info("turn cancelled thread=%s", record.thread_id)
        await blocks.system(record, [blocks.result_block("Run cancelled", "The analysis was cancelled.")])
      except Exception as exc:  # noqa: BLE001 - any worker/LLM failure terminates the turn
        log.exception("turn failed thread=%s", record.thread_id)
        await blocks.system(
            record,
            [blocks.error_block("Agent error", f"{type(exc).__name__}: {exc}", retryable=True)],
        )


async def _run_pipeline(record: ThreadRecord, content: str) -> None:
    settings = get_settings()
    date_range = _analysis_window()

    _check_cancel(record)
    await blocks.assistant(
        record,
        [blocks.text_block("Comparing the campaign metrics against the recent baseline to find signals.")],
    )

    mode = "gemini" if settings.use_real_llm else "stub"
    log.info("pipeline start thread=%s llm=%s window=%s..%s",
             record.thread_id, mode, date_range.start, date_range.end)

    # Reflection (contract 06 §Reflection): advisory summary of past review
    # failures from Phoenix MCP. Off unless PHOENIX_USE_MCP; never blocks the loop
    # (offloaded) and never overrides the deterministic reviewer.
    if settings.reflection_enabled:
        try:
            summary = await asyncio.to_thread(
                reflection.summarize_failures, record.workspace_id, record.campaign_id
            )
            if summary:
                log.info("reflection thread=%s: %s", record.thread_id, summary)
        except Exception as exc:  # noqa: BLE001 - advisory only, never fatal
            log.warning("reflection skipped: %s", exc)

    # --- Stage 1: Analyst (detect signals, then ground them) ---
    _check_cancel(record)
    log.info("[1/4] analyst start (llm=%s)", mode)
    await blocks.assistant(record, [blocks.activity_block("query_metric_baseline", "Checking metric baseline", "running")])
    signal_out = await workers.run_analyst(content, date_range)
    signals: list[Signal] = signal_out.signals
    log.info("[1/4] analyst done: %d signal(s)", len(signals))
    await blocks.assistant(
        record,
        [blocks.activity_block("query_metric_baseline", "Checked metric baseline", "done")],
    )
    for sig in signals:
        await blocks.assistant(
            record,
            [
                blocks.text_block(sig.description),
                blocks.artifact_block(sig.id, "signal", sig.title, sig.model_dump(mode="json")),
            ],
        )

    # --- Stage 2: Strategist (why hypotheses) ---
    _check_cancel(record)
    log.info("[2/4] strategist start")
    await blocks.assistant(record, [blocks.activity_block("search_team_notes", "Searching team notes", "running")])
    hyp_out = await workers.run_strategist(content, signals)
    hypotheses: list[Hypothesis] = hyp_out.hypotheses
    log.info("[2/4] strategist done: %d hypothesis(es)", len(hypotheses))
    await blocks.assistant(record, [blocks.activity_block("search_team_notes", "Checked team notes", "done")])
    for hyp in hypotheses:
        await blocks.assistant(
            record,
            [
                blocks.text_block(hyp.rationale),
                blocks.artifact_block(hyp.id, "hypothesis", hyp.statement, hyp.model_dump(mode="json")),
            ],
        )

    # --- Stage 3 + 4: Writer + Reviewer gate with prefix-reuse backtracking ---
    log.info("[3/4] writer start")
    plan = (await workers.run_writer(content, date_range, hypotheses)).experiment_plan
    log.info("[3/4] writer done: %d item(s)", len(plan.items))
    backtrack_count = 0
    payload: AgentResultPayload
    _gmeta = {
        "thread_id": record.thread_id,
        "workspace_id": record.workspace_id,
        "campaign_id": record.campaign_id,
    }
    while True:
        _check_cancel(record)
        log.info("[4/4] reviewer start")
        payload = formatter.assemble(signals, hypotheses, plan)
        # GUARDRAIL span: deterministic reviewer gate (contract 06 §Reviewer Gate).
        with tracing.guardrail_span(
            "launchpilot.reviewer_gate",
            input_value={"signals": len(signals), "hypotheses": len(hypotheses),
                         "items": len(plan.items)},
            metadata={**_gmeta, "validator_passed": None, "backtrack_count": backtrack_count},
            workspace_id=record.workspace_id,
            campaign_id=record.campaign_id,
        ) as g_span:
            report = reviewer.review(payload)
            tracing.set_output(g_span, report.model_dump(mode="json"))
            tracing.set_metadata(g_span, {**_gmeta, "validator_passed": report.passed,
                                          "backtrack_count": backtrack_count})
            # EVALUATOR span: the deterministic validation summary (pass + codes).
            with tracing.evaluator_span(
                "launchpilot.validation",
                input_value={"signals": len(signals), "hypotheses": len(hypotheses),
                             "items": len(plan.items)},
                metadata={**_gmeta, "backtrack_count": backtrack_count},
                workspace_id=record.workspace_id,
                campaign_id=record.campaign_id,
            ) as e_span:
                tracing.set_output(e_span, {"passed": report.passed,
                                            "issue_codes": [i.code.value for i in report.issues]})
        log.info("[4/4] reviewer passed=%s issues=%d", report.passed, len(report.issues))
        if report.passed:
            break
        if backtrack_count >= settings.backtrack_limit:
            await blocks.system(
                record,
                [blocks.error_block(
                    "Validation failed",
                    f"validation failed after {backtrack_count} backtracks",
                    retryable=True,
                )],
            )
            return
        backtrack_count += 1
        target = failure.route([i.code for i in report.issues])
        log.warning("backtrack #%d -> %s (%s)", backtrack_count, target,
                    "; ".join(i.code.value for i in report.issues))
        await blocks.assistant(
            record,
            [blocks.text_block(f"Found something to improve in review; re-running the {target} step.")],
        )
        # Regenerate from the root cause downstream; earlier good artifacts stay.
        if target in ("analyst", "generator"):
            signals = (await workers.run_analyst(content, date_range)).signals
            hypotheses = (await workers.run_strategist(content, signals)).hypotheses
            plan = (await workers.run_writer(content, date_range, hypotheses)).experiment_plan
        elif target == "strategist":
            hypotheses = (await workers.run_strategist(content, signals)).hypotheses
            plan = (await workers.run_writer(content, date_range, hypotheses)).experiment_plan
        else:  # writer / formatter
            plan = (await workers.run_writer(content, date_range, hypotheses)).experiment_plan

    # --- Done: emit the plan artifact + open the approval gate (Java takes over) ---
    await blocks.assistant(
        record,
        [
            blocks.text_block("The experiment plan draft is ready. Please review and approve."),
            blocks.artifact_block(plan.id, "experiment_plan", plan.summary, plan.model_dump(mode="json")),
        ],
    )
    await blocks.assistant(
        record,
        [blocks.approval_block(
            approval_id(),
            "Approve experiment plan",
            plan.id,
            payload.model_dump(mode="json"),
        )],
    )
    log.info("pipeline done thread=%s approval emitted plan=%s", record.thread_id, plan.id)
