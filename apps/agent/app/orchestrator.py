"""State-reactive orchestrator for Python Agent Core v2.

Each turn resolves scope and bounded memory, interprets free-form text into a
StateDeltaProposal, reduces it into authoritative workflow state, then replies
directly, delegates to a phase facade, or reruns the worker pipeline from the
target phase.

Approve/reject/cancel/revise are resolved in Java and never reach here
(contract 02 README, Action Handling), so this module only ever sees free-form
content turns.

Deterministic review still uses prefix-reuse backtracking on reviewer failure.
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
from app.runtime.repository import (
    DeltaEvent,
    RepositoryConflict,
    RuntimeArtifact,
    get_runtime_repository,
)
from app.runtime.thread_store import ThreadRecord
from app.runtime.state import (
    DelegationMode,
    PhaseType,
    compact_state_summary,
    decide_delegation,
    reduce_state,
    resolve_scope,
)
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


def _thread_context(record: ThreadRecord, has_scope: bool) -> str:
    # State hint that steers direct chat toward the next concrete step.
    has_plan = bool(
        record.state.active_artifact_id
        or record.state.phase_artifacts[PhaseType.EXPERIMENT_PLAN.value].get("experiment_plan")
    )
    if has_plan:
        return "analysis_done"
    if has_scope:
        return "ready_to_analyze"
    return "need_campaign"


async def process_turn(
    record: ThreadRecord, content: str, attachments: tuple = ()
) -> None:
    """Handle one user turn. Safe to launch as a background task.

    Turn setup resolves scope and bounded memory, the interpreter proposes a
    StateDelta, the reducer produces a deterministic delegation decision, and
    the orchestrator either replies directly, delegates, or reruns the pipeline.
    Any failure becomes an error block rather than an unhandled task exception.
    """
    async with record.turn_lock:
        await _process_turn_locked(record, content, attachments)


async def _process_turn_locked(
    record: ThreadRecord, content: str, attachments: tuple = ()
) -> None:
    """Handle a turn while holding the per-thread state lock."""
    repository = get_runtime_repository()
    persisted_state = await repository.load_state(record.thread_id)
    if persisted_state:
        record.state = persisted_state
        if persisted_state.scope:
            record.set_context(persisted_state.scope.workspace_id, persisted_state.scope.campaign_id)
    scope = resolve_scope(record.thread_id, record.workspace_id, record.campaign_id, record.state)
    if scope:
        record.set_context(scope.workspace_id, scope.campaign_id)
        record.state = await repository.create_or_load_state(scope)
        record.state.scope = scope
        campaign_context = await repository.load_campaign_context(scope)
        recent_messages = await repository.load_recent_messages(scope, limit=12)
    else:
        campaign_context = None
        recent_messages = []
    expected_revision = record.state.revision
    has_scope = scope is not None
    context = _thread_context(record, has_scope)
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
        state_summary = compact_state_summary(record.state)
        if campaign_context:
            state_summary += f"; campaign={campaign_context.name or campaign_context.campaign_id}"
        if recent_messages:
            state_summary += f"; recent_messages={len(recent_messages)}"
        delta = await workers.run_turn_interpreter(
            content, f"{context}; {state_summary}", record.state.current_phase
        )
        reducer_decision = reduce_state(record.state, delta, content)
        delegation = decide_delegation(reducer_decision)
        log.info(
            "turn thread=%s intent=%s phase=%s target=%s has_scope=%s content=%r",
            record.thread_id,
            delta.intent.value,
            record.state.current_phase.value,
            record.state.target_phase.value,
            has_scope,
            content[:80],
        )
        tracing.set_metadata(
            turn_span,
            {
                **meta,
                "agent.scope.workspace_id": record.workspace_id,
                "agent.scope.campaign_id": record.campaign_id,
                "agent.state.revision_before": reducer_decision.revision_before,
                "agent.state.revision_after": reducer_decision.revision_after,
                "agent.delta.intent": delta.intent.value,
                "agent.delta.response_mode": delta.response_mode.value,
                "agent.reducer.decision": reducer_decision.decision.value,
                "agent.delegation.mode": delegation.mode.value,
                "agent.repository.backend": repository.backend_name,
                "phase": record.state.current_phase.value,
            },
        )

        if delegation.mode == DelegationMode.CLARIFY:
            reply = (
                delta.clarification_question
                or delta.reply
                or "I can do that, but please confirm the change first."
            )
            await blocks.assistant(record, [blocks.text_block(reply)])
            tracing.set_output(turn_span, {"mode": "clarify", "reply": reply[:500]})
        elif delegation.mode == DelegationMode.RERUN:
            if not scope:
                await blocks.system(
                    record,
                    [blocks.error_block(
                        "Campaign context required",
                        "campaign_id를 확인할 수 없어 분석을 시작하지 않았습니다. 같은 thread에 campaign_id를 포함해 다시 요청해 주세요.",
                        retryable=True,
                    )],
                )
                tracing.set_output(turn_span, {"mode": "rerun", "status": "missing_campaign"})
            elif not campaign_context:
                await blocks.system(
                    record,
                    [blocks.error_block(
                        "Campaign context not found",
                        f"campaign_id={scope.campaign_id} 컨텍스트를 찾지 못해 분석을 시작하지 않았습니다.",
                        retryable=True,
                    )],
                )
                tracing.set_output(turn_span, {"mode": "rerun", "status": "campaign_not_found"})
            else:
                # Analysis no longer requires a fresh CSV: with no upload we analyze
                # the existing baseline data; with an upload we factor it in too.
                # Re-runnable: a later "analyze" starts a fresh pass over updated data.
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
                ) as pipeline_span:
                    summary = await _run_pipeline(record, content, record.state.current_phase, repository)
                    if summary:
                        tracing.set_output(pipeline_span, summary)
                tracing.set_output(turn_span, summary or {"mode": "rerun", "status": "incomplete"})
        elif delegation.mode == DelegationMode.DELEGATE:
            reply = (
                "요청은 현재 단계의 산출물 수정으로 분류했습니다. "
                "세부 phase agent는 다음 구현 범위라서, 지금은 오케스트레이터가 상태와 수정 의도만 안전하게 기록합니다."
            )
            record.state.active_chat_history.append({"role": "assistant", "content": reply})
            await blocks.assistant(record, [blocks.text_block(reply)])
            tracing.set_output(turn_span, {"mode": "delegate", "target_phase": delegation.target_phase.value})
        else:
            # Chat or analysis already done: emit the interpreter's direct reply.
            reply = delta.reply or "How can I help with your campaign analysis?"
            record.state.active_chat_history.append({"role": "assistant", "content": reply})
            log.info(
                "chat reply thread=%s context=%s",
                record.thread_id,
                context,
            )
            await blocks.assistant(record, [blocks.text_block(reply)])
            tracing.set_output(turn_span, {"mode": "direct", "reply": reply[:500]})
        if scope:
            event = DeltaEvent(
                scope=scope,
                proposal=delta,
                reducer_decision={
                    "decision": reducer_decision.decision.value,
                    "delegation_mode": reducer_decision.delegation_mode.value,
                    "reason": reducer_decision.reason,
                    "revision_before": reducer_decision.revision_before,
                    "revision_after": reducer_decision.revision_after,
                },
            )
            try:
                await repository.commit_state(expected_revision, record.state, event)
                tracing.set_metadata(turn_span, {"agent.state_delta.delta_id": event.delta_id})
            except RepositoryConflict:
                tracing.set_metadata(turn_span, {"agent.repository.conflict": True})
                await blocks.system(
                    record,
                    [blocks.error_block(
                        "Agent busy",
                        "동일 thread의 상태가 먼저 갱신되어 이번 턴의 상태 저장을 중단했습니다. 잠시 후 다시 시도해 주세요.",
                        retryable=True,
                    )],
                )
      except _Cancelled:
        log.info("turn cancelled thread=%s", record.thread_id)
        await blocks.system(record, [blocks.result_block("Run cancelled", "The analysis was cancelled.")])
      except Exception as exc:  # noqa: BLE001 - any worker/LLM failure terminates the turn
        log.exception("turn failed thread=%s", record.thread_id)
        await blocks.system(
            record,
            [blocks.error_block("Agent error", f"{type(exc).__name__}: {exc}", retryable=True)],
        )


async def _run_pipeline(
    record: ThreadRecord,
    content: str,
    start_phase: PhaseType = PhaseType.DATA_ANALYSIS,
    repository=None,
) -> dict | None:
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

    if start_phase == PhaseType.DATA_ANALYSIS:
        # --- Stage 1: Analyst (detect signals, then ground them) ---
        record.state.current_phase = PhaseType.DATA_ANALYSIS
        _check_cancel(record)
        log.info("[1/4] analyst start (llm=%s)", mode)
        await blocks.assistant(record, [blocks.activity_block("query_metric_baseline", "Checking metric baseline", "running")])
        signal_out = await workers.run_analyst(content, date_range)
        signals: list[Signal] = signal_out.signals
        record.state.phase_artifacts[PhaseType.DATA_ANALYSIS.value]["signals"] = [
            sig.model_dump(mode="json") for sig in signals
        ]
        await _save_phase_artifact_ref(
            record,
            repository,
            PhaseType.DATA_ANALYSIS,
            "signals",
            {"signals": [sig.model_dump(mode="json") for sig in signals]},
        )
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
    else:
        signals = [
            Signal(**raw)
            for raw in record.state.phase_artifacts[PhaseType.DATA_ANALYSIS.value].get("signals", [])
        ]
        if not signals:
            signals = (await workers.run_analyst(content, date_range)).signals

    # --- Stage 2: Strategist (why hypotheses) ---
    if start_phase in (PhaseType.DATA_ANALYSIS, PhaseType.HYPOTHESIS_GEN):
        record.state.current_phase = PhaseType.HYPOTHESIS_GEN
        _check_cancel(record)
        log.info("[2/4] strategist start")
        await blocks.assistant(record, [blocks.activity_block("search_team_notes", "Searching team notes", "running")])
        hyp_out = await workers.run_strategist(content, signals)
        hypotheses: list[Hypothesis] = hyp_out.hypotheses
        record.state.phase_artifacts[PhaseType.HYPOTHESIS_GEN.value]["hypotheses"] = [
            hyp.model_dump(mode="json") for hyp in hypotheses
        ]
        await _save_phase_artifact_ref(
            record,
            repository,
            PhaseType.HYPOTHESIS_GEN,
            "hypotheses",
            {"hypotheses": [hyp.model_dump(mode="json") for hyp in hypotheses]},
        )
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
    else:
        hypotheses = [
            Hypothesis(**raw)
            for raw in record.state.phase_artifacts[PhaseType.HYPOTHESIS_GEN.value].get("hypotheses", [])
        ]
        if not hypotheses:
            hypotheses = (await workers.run_strategist(content, signals)).hypotheses

    # --- Stage 3 + 4: Writer + Reviewer gate with prefix-reuse backtracking ---
    record.state.current_phase = PhaseType.EXPERIMENT_PLAN
    log.info("[3/4] writer start")
    plan = (await workers.run_writer(content, date_range, hypotheses)).experiment_plan
    record.state.phase_artifacts[PhaseType.EXPERIMENT_PLAN.value]["experiment_plan"] = plan.model_dump(mode="json")
    record.state.active_artifact_id = plan.id
    await _save_phase_artifact_ref(
        record,
        repository,
        PhaseType.EXPERIMENT_PLAN,
        "experiment_plan",
        {"experiment_plan": plan.model_dump(mode="json")},
    )
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
    pending_approval_id = approval_id()
    record.state.pending_approval_id = pending_approval_id
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
            pending_approval_id,
            "Approve experiment plan",
            plan.id,
            payload.model_dump(mode="json"),
        )],
    )
    log.info("pipeline done thread=%s approval emitted plan=%s", record.thread_id, plan.id)
    # Summary used as the CHAIN/AGENT span output.value (Phoenix shows it on the
    # root spans, which otherwise had input only).
    return {
        "plan_id": plan.id,
        "signals": len(signals),
        "hypotheses": len(hypotheses),
        "experiments": len(plan.items),
        "validator_passed": True,
        "backtracks": backtrack_count,
    }


async def _save_phase_artifact_ref(
    record: ThreadRecord,
    repository,
    phase: PhaseType,
    artifact_type: str,
    payload: dict,
) -> None:
    if repository is None or record.state.scope is None:
        return
    artifact = RuntimeArtifact(
        artifact_type=artifact_type,
        phase=phase.value,
        payload=payload,
    )
    ref = await repository.save_runtime_artifact(record.state.scope, artifact)
    refs = record.state.phase_artifact_refs.setdefault(phase.value, [])
    refs.append(ref)
    refs[:] = refs[-6:]
