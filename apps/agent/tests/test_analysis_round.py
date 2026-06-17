"""분석 라운드(DATA_ANALYSIS) 골든 테스트.

리팩터링 전 '현재 동작'을 박제한다. 옳고 그름을 따지지 않고, 지금 이 입력에
대해 지금 이 출력이 나온다는 사실만 잠근다. 이름/구조를 바꾼 뒤에도 이 테스트가
그대로 통과하면 '동작은 안 바뀌었다'가 증명된다.
"""
from __future__ import annotations

import pytest

from app.contracts import DateRange, Signal, SignalDraftOutput
from app.orchestration import phases
from app.orchestration.emitter import StreamEmitter
from app.orchestration.models import TurnContext
from app.orchestration.phases import AnalysisRoundRunner, PhaseArtifactStore
from app.runtime.state_cache import get_state_cache
from app.runtime.repository import InMemoryAgentRuntimeRepository
from app.runtime.state import PhaseType, ScopeContext
from app.runtime.thread_store import ThreadRecord


def _signal() -> Signal:
    return Signal(
        id="sig_save_rate",
        type="lift",
        title="Save rate lift",
        description="저장률이 기준선 대비 상승했습니다.",
        metric_name="save_rate",
        current_value=0.18,
        baseline_value=0.12,
        lift_ratio=1.5,
        date_window=DateRange(start="2026-06-01", end="2026-06-07"),
        confidence="high",
        evidence_refs=["ev_1"],
    )


def _turn() -> TurnContext:
    scope = ScopeContext(workspace_id="demo_workspace", campaign_id="camp_1", thread_id="thread_x")
    record = ThreadRecord(thread_id="thread_x", workspace_id="demo_workspace", campaign_id="camp_1")
    record.state.scope = scope
    return TurnContext(
        record=record,
        content="이 캠페인 분석해줘",
        attachments=(),
        repository=InMemoryAgentRuntimeRepository(),
        state_cache=get_state_cache(),
        scope=scope,
    )


def _blocks(record: ThreadRecord) -> list[dict]:
    """기록된 모든 메시지의 블록을 한 줄로 편다."""
    return [block for message in record.messages for block in message.blocks]


async def test_analysis_round_emits_signal_and_saves_artifact(monkeypatch: pytest.MonkeyPatch) -> None:
    # 가짜 분석가: LLM 대신 고정 신호 하나를 돌려준다.
    async def fake_run_analyst(content, date_range, memory_context=None):
        return SignalDraftOutput(signals=[_signal()])

    monkeypatch.setattr(phases.workers, "run_analyst", fake_run_analyst)

    turn = _turn()
    runner = AnalysisRoundRunner(StreamEmitter(), PhaseArtifactStore())
    outcome = runner.phase  # 단계 식별자 확인용
    result = await runner.run(turn)

    # 1) 결과 요약
    assert result.trace_output == {"phase": "DATA_ANALYSIS", "signals": 1}

    # 2) 현재 단계가 분석으로 설정됨
    assert turn.record.state.current_phase == PhaseType.DATA_ANALYSIS
    assert outcome == PhaseType.DATA_ANALYSIS

    # 3) 신호가 상태에 저장됨
    saved = turn.record.state.phase_artifacts[PhaseType.DATA_ANALYSIS.value]["signals"]
    assert len(saved) == 1 and saved[0]["id"] == "sig_save_rate"

    # 4) 신호 아티팩트가 저장소에 들어가고, 참조가 상태에 남음
    refs = turn.record.state.phase_artifact_refs[PhaseType.DATA_ANALYSIS.value]
    assert len(refs) == 1

    # 5) 사용자에게 신호 아티팩트 블록이 스트리밍됨
    blocks = _blocks(turn.record)
    artifact_blocks = [b for b in blocks if b.get("kind") == "artifact"]
    assert any(b["artifact_kind"] == "signal" and b["id"] == "sig_save_rate" for b in artifact_blocks)


async def test_analysis_round_handles_no_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    # 신호가 0개여도 스레드가 죽지 않고 'no_signals'로 정상 종료해야 한다.
    async def fake_run_analyst(content, date_range, memory_context=None):
        # 빈 신호 목록은 SignalDraftOutput(min_length=1) 계약을 위반 -> ValidationError.
        # 실제 분석가도 같은 방식으로 빈 출력을 거른다.
        return SignalDraftOutput(signals=[])

    monkeypatch.setattr(phases.workers, "run_analyst", fake_run_analyst)

    turn = _turn()
    runner = AnalysisRoundRunner(StreamEmitter(), PhaseArtifactStore())
    result = await runner.run(turn)

    assert result.trace_output["status"] == "no_signals"
    assert result.trace_output["signals"] == 0
