"""SKIP_SUBMIT 리듀서 골든 테스트.

전문가용 명시적 스킵(issue #25 논의) — 사용자가 완성 산출물이나 힌트를 직접
던졌을 때, 코드(리듀서)가 그것을 어떻게 반영하는지를 잠근다. LLM/워커 호출
없이 순수 리듀서 로직만 검증한다.
"""
from __future__ import annotations

import pytest

from app.contracts import ExperimentPlanDraftOutput, ValidationReport
from app.orchestration import phases
from app.orchestration.emitter import StreamEmitter
from app.orchestration.models import TurnContext
from app.orchestration.phases import PhaseArtifactStore, PlanRoundRunner
from app.runtime.repository import InMemoryAgentRuntimeRepository
from app.runtime.state import (
    ChangeDecisionType,
    ConversationState,
    PhaseType,
    ProposedChange,
    ScopeContext,
    SkipSubtype,
    TurnIntent,
    apply_proposed_change,
)
from app.runtime.state_cache import get_state_cache
from app.runtime.thread_store import ThreadRecord


def _plan():
    from app.contracts import ExperimentItem, ExperimentPlan

    item = ExperimentItem(
        id="exp_1",
        hypothesis_id="hyp_1",
        title="hook A/B",
        channel="youtube",
        content_format="short",
        hook="first 3s",
        cta="subscribe",
        target_metric="save_rate",
        success_criteria="save_rate +10%",
        scheduled_at="2026-06-20",
        production_brief="brief",
    )
    return ExperimentPlan(id="plan_1", summary="next week", overall_confidence="medium", items=[item])


def _state_with_signal() -> ConversationState:
    state = ConversationState()
    state.phase_artifacts[PhaseType.DATA_ANALYSIS.value]["signals"] = [
        {
            "id": "sig_save_rate",
            "type": "lift",
            "title": "Save rate lift",
            "description": "desc",
            "metric_name": "save_rate",
            "current_value": 0.18,
            "baseline_value": 0.12,
            "lift_ratio": 1.5,
            "date_window": {"start": "2026-06-01", "end": "2026-06-07"},
            "confidence": "high",
            "evidence_refs": ["ev_1"],
        }
    ]
    return state


def test_full_artifact_skip_materializes_hypothesis_and_jumps_to_plan():
    state = _state_with_signal()
    delta = ProposedChange(
        intent=TurnIntent.SKIP_SUBMIT,
        target_phase=PhaseType.EXPERIMENT_PLAN,
        skip_subtype=SkipSubtype.FULL_ARTIFACT,
        skip_payload="20s eitaleun almimpiro ttaemun",
    )

    decision = apply_proposed_change(state, delta, "skip please")

    assert decision.decision == ChangeDecisionType.ACCEPTED
    hypotheses = state.phase_artifacts[PhaseType.HYPOTHESIS_GEN.value]["hypotheses"]
    assert len(hypotheses) == 1
    assert hypotheses[0]["statement"] == "20s eitaleun almimpiro ttaemun"
    assert hypotheses[0]["signal_ids"] == ["sig_save_rate"]
    assert "User-supplied" in hypotheses[0]["caveats"][0]
    assert state.target_phase == PhaseType.EXPERIMENT_PLAN
    assert state.current_phase == PhaseType.EXPERIMENT_PLAN


def test_full_artifact_skip_blocked_without_signals():
    state = ConversationState()
    delta = ProposedChange(
        intent=TurnIntent.SKIP_SUBMIT,
        target_phase=PhaseType.EXPERIMENT_PLAN,
        skip_subtype=SkipSubtype.FULL_ARTIFACT,
        skip_payload="some hypothesis",
    )

    apply_proposed_change(state, delta, "skip please")

    assert not state.phase_artifacts[PhaseType.HYPOTHESIS_GEN.value].get("hypotheses")
    assert state.current_phase == PhaseType.DATA_ANALYSIS
    assert delta.reply is not None and "분석" in delta.reply


def test_partial_input_skip_seeds_hypothesis_context_without_materializing():
    state = _state_with_signal()
    delta = ProposedChange(
        intent=TurnIntent.SKIP_SUBMIT,
        target_phase=PhaseType.HYPOTHESIS_GEN,
        skip_subtype=SkipSubtype.PARTIAL_INPUT,
        skip_payload="notification fatigue related",
    )

    apply_proposed_change(state, delta, "here's a hint")

    assert state.hypothesis_context.user_hunch == "notification fatigue related"
    assert not state.phase_artifacts[PhaseType.HYPOTHESIS_GEN.value].get("hypotheses")
    assert state.target_phase == PhaseType.HYPOTHESIS_GEN


def test_skip_missing_payload_is_rejected():
    state = _state_with_signal()
    delta = ProposedChange(
        intent=TurnIntent.SKIP_SUBMIT,
        target_phase=PhaseType.EXPERIMENT_PLAN,
        skip_subtype=SkipSubtype.FULL_ARTIFACT,
        skip_payload="   ",
    )

    apply_proposed_change(state, delta, "skip")

    assert not state.phase_artifacts[PhaseType.HYPOTHESIS_GEN.value].get("hypotheses")
    assert delta.reply is not None and "받지 못했어요" in delta.reply


def test_skip_target_must_be_hypothesis_or_plan():
    state = _state_with_signal()
    delta = ProposedChange(
        intent=TurnIntent.SKIP_SUBMIT,
        target_phase=PhaseType.DATA_ANALYSIS,
        skip_subtype=SkipSubtype.FULL_ARTIFACT,
        skip_payload="something",
    )

    apply_proposed_change(state, delta, "skip")

    assert not state.phase_artifacts[PhaseType.HYPOTHESIS_GEN.value].get("hypotheses")
    assert delta.reply is not None and "가설 수립 또는 실험 계획" in delta.reply


async def test_full_artifact_skip_flows_into_plan_round_without_strategist(
    monkeypatch: pytest.MonkeyPatch,
):
    # 스킵으로 EXPERIMENT_PLAN까지 넘어가면, 기존 계획 러너가 손 안 대고 그대로
    # 이 가설을 재료 삼아 돈다 — 전략가는 아예 다시 불리지 않는다.
    scope = ScopeContext(workspace_id="demo_workspace", campaign_id="camp_1", thread_id="thread_x")
    record = ThreadRecord(thread_id="thread_x", workspace_id="demo_workspace", campaign_id="camp_1")
    record.state.scope = scope
    turn = TurnContext(
        record=record,
        content="skip strategist, use this hypothesis",
        attachments=(),
        repository=InMemoryAgentRuntimeRepository(),
        state_cache=get_state_cache(),
        scope=scope,
    )
    turn.record.state.phase_artifacts[PhaseType.DATA_ANALYSIS.value]["signals"] = [
        {
            "id": "sig_save_rate",
            "type": "lift",
            "title": "Save rate lift",
            "description": "desc",
            "metric_name": "save_rate",
            "current_value": 0.18,
            "baseline_value": 0.12,
            "lift_ratio": 1.5,
            "date_window": {"start": "2026-06-01", "end": "2026-06-07"},
            "confidence": "high",
            "evidence_refs": ["ev_1"],
        }
    ]

    delta = ProposedChange(
        intent=TurnIntent.SKIP_SUBMIT,
        target_phase=PhaseType.EXPERIMENT_PLAN,
        skip_subtype=SkipSubtype.FULL_ARTIFACT,
        skip_payload="notification fatigue drives the drop",
    )
    apply_proposed_change(turn.record.state, delta, "skip strategist, use this hypothesis")
    assert turn.record.state.current_phase == PhaseType.EXPERIMENT_PLAN

    strategist_called = False

    async def fake_run_strategist(*args, **kwargs):
        nonlocal strategist_called
        strategist_called = True
        raise AssertionError("strategist should not run when the hypothesis was skipped in")

    async def fake_run_writer(content, date_range, hypotheses, memory_context=None):
        assert len(hypotheses) == 1
        assert hypotheses[0].statement == "notification fatigue drives the drop"
        return ExperimentPlanDraftOutput(experiment_plan=_plan())

    monkeypatch.setattr(phases.workers, "run_strategist", fake_run_strategist)
    monkeypatch.setattr(phases.workers, "run_writer", fake_run_writer)
    monkeypatch.setattr(
        phases.reviewer,
        "review",
        lambda payload: ValidationReport(passed=True, severity="none", issues=[]),
    )

    runner = PlanRoundRunner(StreamEmitter(), PhaseArtifactStore())
    result = await runner.run(turn)

    assert not strategist_called
    assert result.trace_output["validator_passed"] is True
    assert result.trace_output["plan_id"] == "plan_1"


def test_reuse_prior_relies_on_existing_hypotheses_guard():
    state = _state_with_signal()
    state.phase_artifacts[PhaseType.HYPOTHESIS_GEN.value]["hypotheses"] = [
        {
            "id": "hyp_existing",
            "signal_ids": ["sig_save_rate"],
            "statement": "already made",
            "rationale": "r",
            "confidence": "medium",
            "supporting_evidence_refs": [],
            "caveats": ["c"],
        }
    ]
    delta = ProposedChange(
        intent=TurnIntent.SKIP_SUBMIT,
        target_phase=PhaseType.EXPERIMENT_PLAN,
        skip_subtype=SkipSubtype.REUSE_PRIOR,
    )

    decision = apply_proposed_change(state, delta, "use the one from before")

    assert decision.decision == ChangeDecisionType.ACCEPTED
    # unchanged: reuse_prior does not overwrite existing hypotheses
    assert state.phase_artifacts[PhaseType.HYPOTHESIS_GEN.value]["hypotheses"][0]["id"] == "hyp_existing"
    assert state.target_phase == PhaseType.EXPERIMENT_PLAN
