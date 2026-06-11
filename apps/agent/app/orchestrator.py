"""State-reactive orchestrator for Python Agent Core v2.

Each turn resolves scope and bounded memory, interprets free-form text into a
StateDeltaProposal, reduces it into authoritative workflow state, then replies
directly, delegates to a phase facade, or reruns the worker pipeline from the
target phase.

Approve/reject/cancel/revise are resolved in Java and never reach here
(contract 02 README, Action Handling), so this module only ever sees free-form
content turns.

Deterministic review validates plan drafts only when the user explicitly asks
for the experiment planning round. Cancellation is checked between stages
(best-effort).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from app.agents import formatter, reflection, reviewer, workers
from app.tools import evidence
from app.contracts import (
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


async def _progress(
    record: ThreadRecord,
    activity_id: str,
    title: str,
    status: str,
    detail: str | None = None,
) -> None:
    """Emit user-safe work progress over the thread stream.

    These are lifecycle/status events, not chain-of-thought. They let the user
    see where the turn is spending time and decide whether to stop/re-steer.
    """
    await blocks.assistant(record, [blocks.activity_block(activity_id, title, status, detail)])


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
        return "plan_ready"
    has_signals = bool(record.state.phase_artifacts[PhaseType.DATA_ANALYSIS.value].get("signals"))
    if has_signals:
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
    await _progress(record, "turn.load_state", "Loading thread state", "running")
    persisted_state = await repository.load_state(record.thread_id)
    if persisted_state:
        record.state = persisted_state
        if persisted_state.scope:
            record.set_context(persisted_state.scope.workspace_id, persisted_state.scope.campaign_id)
    await _progress(record, "turn.load_state", "Loaded thread state", "done")

    await _progress(record, "turn.resolve_scope", "Resolving campaign context", "running")
    scope = resolve_scope(record.thread_id, record.workspace_id, record.campaign_id, record.state)
    if scope:
        record.set_context(scope.workspace_id, scope.campaign_id)
        record.state = await repository.create_or_load_state(scope)
        record.state.scope = scope
        campaign_context = await repository.load_campaign_context(scope)
        recent_messages = await repository.load_recent_messages(scope, limit=12)
        await _progress(
            record,
            "turn.resolve_scope",
            "Resolved campaign context",
            "done",
            f"{scope.workspace_id}/{scope.campaign_id}",
        )
        await _progress(
            record,
            "turn.load_memory",
            "Loaded recent conversation memory",
            "done",
            f"{len(recent_messages)} message(s)",
        )
    else:
        campaign_context = None
        recent_messages = []
        await _progress(record, "turn.resolve_scope", "Campaign context missing", "failed")
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
        await _progress(record, "turn.interpret", "Interpreting user request", "running")
        delta = await workers.run_turn_interpreter(
            content, f"{context}; {state_summary}", record.state.current_phase
        )
        await _progress(
            record,
            "turn.interpret",
            "Interpreted user request",
            "done",
            f"{delta.intent.value} / {delta.response_mode.value}",
        )
        await _progress(record, "state.reduce", "Applying workflow guardrails", "running")
        reducer_decision = reduce_state(record.state, delta, content)
        delegation = decide_delegation(reducer_decision)
        await _progress(
            record,
            "state.reduce",
            "Applied workflow guardrails",
            "done",
            f"{reducer_decision.decision.value} -> {delegation.mode.value}",
        )
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
                # Scope every evidence query in this round to the turn's campaign +
                # analysis window. A single user round runs one requested phase;
                # analysis never cascades into hypotheses, planning, or approval.
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
                    await _progress(
                        record,
                        "round.dispatch",
                        f"Starting {record.state.current_phase.value} round",
                        "running",
                    )
                    summary = await _run_pipeline(record, content, record.state.current_phase, repository)
                    if summary:
                        tracing.set_output(pipeline_span, summary)
                    await _progress(
                        record,
                        "round.dispatch",
                        f"Finished {record.state.current_phase.value} round",
                        "done",
                    )
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
            reply = _artifact_lookup_reply(record, delta.intent) or delta.reply or "How can I help with your campaign analysis?"
            record.state.active_chat_history.append({"role": "assistant", "content": reply})
            log.info(
                "chat reply thread=%s context=%s",
                record.thread_id,
                context,
            )
            await blocks.assistant(record, [blocks.text_block(reply)])
            tracing.set_output(turn_span, {"mode": "direct", "reply": reply[:500]})
        if scope:
            await _progress(record, "state.commit", "Saving thread state", "running")
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
                await _progress(record, "state.commit", "Saved thread state", "done", event.delta_id)
            except RepositoryConflict:
                tracing.set_metadata(turn_span, {"agent.repository.conflict": True})
                await _progress(record, "state.commit", "Thread state changed elsewhere", "failed")
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
    """Run exactly one user-requested phase round.

    ADR-004 models LaunchPilot as a round-based HITL workflow. A request for
    analysis must not automatically generate hypotheses, draft a plan, and open
    approval. Each phase advances only when the user asks for that phase.
    """
    date_range = _analysis_window()
    log.info("round start thread=%s phase=%s window=%s..%s", record.thread_id, start_phase.value, date_range.start, date_range.end)

    if start_phase == PhaseType.DATA_ANALYSIS:
        return await _run_analysis_round(record, content, date_range, repository)
    if start_phase == PhaseType.HYPOTHESIS_GEN:
        return await _run_hypothesis_round(record, content, repository)
    if start_phase == PhaseType.EXPERIMENT_PLAN:
        return await _run_plan_round(record, content, date_range, repository)

    await blocks.assistant(record, [blocks.text_block("실험 평가 단계는 아직 실행 결과 입력 후 분석 라운드에서 다룹니다.")])
    return {"mode": "phase_not_implemented", "phase": start_phase.value}


async def _run_analysis_round(record: ThreadRecord, content: str, date_range: DateRange, repository) -> dict:
    _check_cancel(record)
    record.state.current_phase = PhaseType.DATA_ANALYSIS
    await blocks.assistant(record, [blocks.text_block("Comparing the campaign metrics against the recent baseline to find signals.")])
    log.info("[analysis] analyst start (llm=gemini)")
    await _progress(record, "analysis.prepare", "Preparing analysis window", "done", f"{date_range.start}..{date_range.end}")
    await _progress(record, "analysis.evidence", "Checking metric baseline and campaign evidence", "running")
    await _progress(record, "analysis.draft", "Drafting signal analysis with Gemini", "running")
    signal_out = await workers.run_analyst(content, date_range)
    await _progress(record, "analysis.draft", "Drafted signal analysis", "done")
    signals: list[Signal] = signal_out.signals
    record.state.phase_artifacts[PhaseType.DATA_ANALYSIS.value]["signals"] = [sig.model_dump(mode="json") for sig in signals]
    await _progress(record, "artifact.save.analysis", "Saving analysis artifacts", "running", f"{len(signals)} signal(s)")
    await _save_phase_artifact_ref(record, repository, PhaseType.DATA_ANALYSIS, "signals", {"signals": [sig.model_dump(mode="json") for sig in signals]})
    await _progress(record, "artifact.save.analysis", "Saved analysis artifacts", "done", f"{len(signals)} signal(s)")
    log.info("[analysis] analyst done: %d signal(s)", len(signals))
    await _progress(record, "analysis.evidence", "Checked metric baseline and campaign evidence", "done")
    for sig in signals:
        await blocks.assistant(record, [blocks.text_block(sig.description), blocks.artifact_block(sig.id, "signal", sig.title, sig.model_dump(mode="json"))])
    await blocks.assistant(record, [blocks.text_block("분석 결과를 확인했습니다. 원하면 이 신호를 바탕으로 가설을 세울 수 있습니다.")])
    return {"phase": PhaseType.DATA_ANALYSIS.value, "signals": len(signals)}


async def _run_hypothesis_round(record: ThreadRecord, content: str, repository) -> dict | None:
    _check_cancel(record)
    record.state.current_phase = PhaseType.HYPOTHESIS_GEN
    signals = [Signal(**raw) for raw in record.state.phase_artifacts[PhaseType.DATA_ANALYSIS.value].get("signals", [])]
    if not signals:
        await blocks.system(record, [blocks.error_block("Analysis required", "가설을 세우기 전에 먼저 데이터 분석 라운드를 실행해 주세요.", retryable=True)])
        return {"phase": PhaseType.HYPOTHESIS_GEN.value, "status": "missing_analysis"}

    log.info("[hypothesis] strategist start")
    await _progress(record, "hypothesis.load_signals", "Loaded prior signal artifacts", "done", f"{len(signals)} signal(s)")
    await _progress(record, "hypothesis.evidence", "Checking team context", "running")
    await _progress(record, "hypothesis.draft", "Drafting hypotheses with Gemini", "running")
    hyp_out = await workers.run_strategist(content, signals)
    await _progress(record, "hypothesis.draft", "Drafted hypotheses", "done")
    hypotheses: list[Hypothesis] = hyp_out.hypotheses
    record.state.phase_artifacts[PhaseType.HYPOTHESIS_GEN.value]["hypotheses"] = [hyp.model_dump(mode="json") for hyp in hypotheses]
    await _progress(record, "artifact.save.hypothesis", "Saving hypothesis artifacts", "running", f"{len(hypotheses)} hypothesis(es)")
    await _save_phase_artifact_ref(record, repository, PhaseType.HYPOTHESIS_GEN, "hypotheses", {"hypotheses": [hyp.model_dump(mode="json") for hyp in hypotheses]})
    await _progress(record, "artifact.save.hypothesis", "Saved hypothesis artifacts", "done", f"{len(hypotheses)} hypothesis(es)")
    log.info("[hypothesis] strategist done: %d hypothesis(es)", len(hypotheses))
    await _progress(record, "hypothesis.evidence", "Checked team context", "done")
    for hyp in hypotheses:
        await blocks.assistant(record, [blocks.text_block(hyp.rationale), blocks.artifact_block(hyp.id, "hypothesis", hyp.statement, hyp.model_dump(mode="json"))])
    await blocks.assistant(record, [blocks.text_block("가설을 정리했습니다. 특정 가설을 선택하면 그때 실험 계획을 세울 수 있습니다.")])
    return {"phase": PhaseType.HYPOTHESIS_GEN.value, "hypotheses": len(hypotheses)}


async def _run_plan_round(record: ThreadRecord, content: str, date_range: DateRange, repository) -> dict | None:
    _check_cancel(record)
    record.state.current_phase = PhaseType.EXPERIMENT_PLAN
    signals = [Signal(**raw) for raw in record.state.phase_artifacts[PhaseType.DATA_ANALYSIS.value].get("signals", [])]
    hypotheses = [Hypothesis(**raw) for raw in record.state.phase_artifacts[PhaseType.HYPOTHESIS_GEN.value].get("hypotheses", [])]
    if not signals or not hypotheses:
        await blocks.system(record, [blocks.error_block("Hypotheses required", "실험 계획을 세우기 전에 분석과 가설 라운드를 먼저 완료해 주세요.", retryable=True)])
        return {"phase": PhaseType.EXPERIMENT_PLAN.value, "status": "missing_hypotheses"}

    log.info("[plan] writer start")
    await _progress(
        record,
        "plan.load_context",
        "Loaded signals and hypotheses for planning",
        "done",
        f"{len(signals)} signal(s), {len(hypotheses)} hypothesis(es)",
    )
    await _progress(record, "plan.draft", "Drafting experiment plan with Gemini", "running")
    plan = (await workers.run_writer(content, date_range, hypotheses)).experiment_plan
    await _progress(record, "plan.draft", "Drafted experiment plan", "done", f"{len(plan.items)} experiment(s)")
    record.state.phase_artifacts[PhaseType.EXPERIMENT_PLAN.value]["experiment_plan"] = plan.model_dump(mode="json")
    record.state.active_artifact_id = plan.id
    await _progress(record, "artifact.save.plan", "Saving experiment plan artifact", "running", plan.id)
    await _save_phase_artifact_ref(record, repository, PhaseType.EXPERIMENT_PLAN, "experiment_plan", {"experiment_plan": plan.model_dump(mode="json")})
    await _progress(record, "artifact.save.plan", "Saved experiment plan artifact", "done", plan.id)
    log.info("[plan] writer done: %d item(s)", len(plan.items))

    payload = formatter.assemble(signals, hypotheses, plan)
    await _progress(record, "plan.review", "Checking approval guardrails", "running")
    _gmeta = {"thread_id": record.thread_id, "workspace_id": record.workspace_id, "campaign_id": record.campaign_id}
    with tracing.guardrail_span(
        "launchpilot.reviewer_gate",
        input_value={"signals": len(signals), "hypotheses": len(hypotheses), "items": len(plan.items)},
        metadata={**_gmeta, "validator_passed": None, "backtrack_count": 0},
        workspace_id=record.workspace_id,
        campaign_id=record.campaign_id,
    ) as g_span:
        report = reviewer.review(payload)
        tracing.set_output(g_span, report.model_dump(mode="json"))
        tracing.set_metadata(g_span, {**_gmeta, "validator_passed": report.passed, "backtrack_count": 0})
    log.info("[plan] reviewer passed=%s issues=%d", report.passed, len(report.issues))
    if not report.passed:
        await _progress(record, "plan.review", "Approval guardrails failed", "failed", f"{len(report.issues)} issue(s)")
        await blocks.system(record, [blocks.error_block("Validation failed", "; ".join(issue.message for issue in report.issues), retryable=True)])
        return {"phase": PhaseType.EXPERIMENT_PLAN.value, "validator_passed": False}
    await _progress(record, "plan.review", "Approval guardrails passed", "done")

    pending_approval_id = approval_id()
    record.state.pending_approval_id = pending_approval_id
    await blocks.assistant(record, [blocks.text_block("The experiment plan draft is ready. Please review and approve."), blocks.artifact_block(plan.id, "experiment_plan", plan.summary, plan.model_dump(mode="json"))])
    await blocks.assistant(record, [blocks.approval_block(pending_approval_id, "Approve experiment plan", plan.id, payload.model_dump(mode="json"))])
    log.info("plan round done thread=%s approval emitted plan=%s", record.thread_id, plan.id)
    return {"phase": PhaseType.EXPERIMENT_PLAN.value, "plan_id": plan.id, "experiments": len(plan.items), "validator_passed": True}


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


def _artifact_lookup_reply(record: ThreadRecord, intent) -> str | None:
    if intent.value != "ARTIFACT_QUERY":
        return None

    raw_plan = record.state.phase_artifacts.get(PhaseType.EXPERIMENT_PLAN.value, {}).get("experiment_plan")
    if not isinstance(raw_plan, dict):
        return "아직 이 thread에서 확인할 수 있는 승인된 실험 계획이 없습니다."

    title = raw_plan.get("summary") or raw_plan.get("id") or "승인된 실험 계획"
    items = raw_plan.get("items") if isinstance(raw_plan.get("items"), list) else []
    if not items:
        return f"승인된 내용은 `{title}` 실험 계획입니다. 세부 실험 항목은 현재 runtime artifact에서 확인되지 않습니다."

    lines = [f"승인한 내용은 `{title}` 기준의 실험 계획입니다."]
    for index, item in enumerate(items[:3], start=1):
        if not isinstance(item, dict):
            continue
        item_title = item.get("title") or item.get("id") or f"실험 {index}"
        channel = item.get("channel")
        scheduled_at = item.get("scheduled_at")
        success = item.get("success_criteria")
        detail = f"{index}. {item_title}"
        if channel:
            detail += f" ({channel})"
        if scheduled_at:
            detail += f", scheduled_at={scheduled_at}"
        if success:
            detail += f", success={success}"
        lines.append(detail)
    return "\n".join(lines)
