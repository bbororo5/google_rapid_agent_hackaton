"""가설/계획 라운드 골든 테스트.

분석 라운드(test_analysis_round.py)와 같은 취지: 리팩터 전 동작을 박제한다.
가설/계획 러너는 구조가 더 복잡해(승인 관문 포함) 별도로 잠근다.
"""
from __future__ import annotations

import pytest

from app.contracts import (
    DateRange,
    ExperimentItem,
    ExperimentPlan,
    ExperimentPlanDraftOutput,
    Hypothesis,
    HypothesisDraftOutput,
    Signal,
    ValidationReport,
)
from app.orchestration import phases
from app.orchestration.emitter import StreamEmitter
from app.orchestration.models import TurnContext
from app.orchestration.phases import (
    HypothesisRoundRunner,
    PhaseArtifactStore,
    PlanRoundRunner,
)
from app.runtime.state_cache import get_state_cache
from app.runtime.repository import InMemoryAgentRuntimeRepository
from app.runtime.state import PhaseType, ScopeContext
from app.runtime.thread_store import ThreadRecord


def _signal() -> Signal:
    return Signal(
        id="sig_save_rate",
        type="lift",
        title="Save rate lift",
        description="저장률 상승.",
        metric_name="save_rate",
        current_value=0.18,
        baseline_value=0.12,
        lift_ratio=1.5,
        date_window=DateRange(start="2026-06-01", end="2026-06-07"),
        confidence="high",
        evidence_refs=["ev_1"],
    )


def _hypothesis() -> Hypothesis:
    return Hypothesis(
        id="hyp_hook",
        signal_ids=["sig_save_rate"],
        statement="훅을 바꾸면 저장률이 오른다.",
        rationale="저장률 신호가 강하다.",
        confidence="medium",
        supporting_evidence_refs=["ev_1"],
        caveats=[],
    )


def _plan() -> ExperimentPlan:
    item = ExperimentItem(
        id="exp_1",
        hypothesis_id="hyp_hook",
        title="새 훅 A/B",
        channel="youtube",
        content_format="short",
        hook="첫 3초 훅",
        cta="구독",
        target_metric="save_rate",
        success_criteria="저장률 +10%",
        scheduled_at="2026-06-20",
        production_brief="제작 메모.",
    )
    return ExperimentPlan(id="plan_1", summary="다음 주 실험", overall_confidence="medium", items=[item])


def _turn() -> TurnContext:
    scope = ScopeContext(workspace_id="demo_workspace", campaign_id="camp_1", thread_id="thread_x")
    record = ThreadRecord(thread_id="thread_x", workspace_id="demo_workspace", campaign_id="camp_1")
    record.state.scope = scope
    return TurnContext(
        record=record,
        content="이어서 진행해줘",
        attachments=(),
        repository=InMemoryAgentRuntimeRepository(),
        state_cache=get_state_cache(),
        scope=scope,
    )


def _blocks(record: ThreadRecord) -> list[dict]:
    return [block for message in record.messages for block in message.blocks]


# --- 가설 라운드 ----------------------------------------------------------

async def test_hypothesis_round_needs_signals_first() -> None:
    # 신호가 없으면 분석 먼저 하라고 안내하고 끝낸다.
    turn = _turn()
    runner = HypothesisRoundRunner(StreamEmitter(), PhaseArtifactStore())
    result = await runner.run(turn)
    assert result.trace_output["status"] == "missing_analysis"


async def test_hypothesis_round_generates_and_saves(monkeypatch: pytest.MonkeyPatch) -> None:
    turn = _turn()
    # 앞선 분석이 신호를 남겨 둔 상태로 시작.
    turn.record.state.phase_artifacts[PhaseType.DATA_ANALYSIS.value]["signals"] = [
        _signal().model_dump(mode="json")
    ]

    async def fake_run_strategist(content, signals, memory_context=None):
        assert len(signals) == 1  # 저장된 신호가 전략가에게 전달됨
        return HypothesisDraftOutput(hypotheses=[_hypothesis()])

    monkeypatch.setattr(phases.workers, "run_strategist", fake_run_strategist)

    result = await runner_run(HypothesisRoundRunner, turn)
    assert result.trace_output == {"phase": "HYPOTHESIS_GEN", "hypotheses": 1}
    saved = turn.record.state.phase_artifacts[PhaseType.HYPOTHESIS_GEN.value]["hypotheses"]
    assert saved[0]["id"] == "hyp_hook"
    artifacts = [b for b in _blocks(turn.record) if b.get("kind") == "artifact"]
    assert any(b["artifact_kind"] == "hypothesis" and b["id"] == "hyp_hook" for b in artifacts)


# --- 계획 라운드 ----------------------------------------------------------

def _seed_signals_and_hypotheses(turn: TurnContext) -> None:
    turn.record.state.phase_artifacts[PhaseType.DATA_ANALYSIS.value]["signals"] = [
        _signal().model_dump(mode="json")
    ]
    turn.record.state.phase_artifacts[PhaseType.HYPOTHESIS_GEN.value]["hypotheses"] = [
        _hypothesis().model_dump(mode="json")
    ]


async def test_plan_round_needs_hypotheses_first() -> None:
    turn = _turn()
    runner = PlanRoundRunner(StreamEmitter(), PhaseArtifactStore())
    result = await runner.run(turn)
    assert result.trace_output["status"] == "missing_hypotheses"


async def test_plan_round_drafts_and_requests_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    turn = _turn()
    _seed_signals_and_hypotheses(turn)

    async def fake_run_writer(content, date_range, hypotheses, memory_context=None):
        return ExperimentPlanDraftOutput(experiment_plan=_plan())

    monkeypatch.setattr(phases.workers, "run_writer", fake_run_writer)
    # 가드레일은 통과시킨다 (reviewer 자체 로직은 별도 테스트 영역).
    monkeypatch.setattr(
        phases.reviewer,
        "review",
        lambda payload: ValidationReport(passed=True, severity="none", issues=[]),
    )

    result = await runner_run(PlanRoundRunner, turn)
    assert result.trace_output["validator_passed"] is True
    assert result.trace_output["plan_id"] == "plan_1"
    assert result.trace_output["experiments"] == 1
    assert turn.record.state.active_artifact_id == "plan_1"
    approvals = [b for b in _blocks(turn.record) if b.get("kind") == "approval"]
    assert len(approvals) == 1 and approvals[0]["target_id"] == "plan_1"


async def test_plan_round_blocks_on_failed_guardrail(monkeypatch: pytest.MonkeyPatch) -> None:
    turn = _turn()
    _seed_signals_and_hypotheses(turn)

    async def fake_run_writer(content, date_range, hypotheses, memory_context=None):
        return ExperimentPlanDraftOutput(experiment_plan=_plan())

    monkeypatch.setattr(phases.workers, "run_writer", fake_run_writer)
    monkeypatch.setattr(
        phases.reviewer,
        "review",
        lambda payload: ValidationReport(passed=False, severity="blocking", issues=[]),
    )

    result = await runner_run(PlanRoundRunner, turn)
    assert result.trace_output["validator_passed"] is False
    # 승인 블록은 나오지 않는다.
    assert not [b for b in _blocks(turn.record) if b.get("kind") == "approval"]


async def runner_run(runner_cls, turn: TurnContext):
    runner = runner_cls(StreamEmitter(), PhaseArtifactStore())
    return await runner.run(turn)
