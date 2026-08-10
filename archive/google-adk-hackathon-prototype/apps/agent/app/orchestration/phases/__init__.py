"""라운드 러너 패키지.

한 단계를 한 번 실행하는 러너를 단계별 파일로 나눴다 (이야기처럼 읽히도록):

  analysis.py     분석 라운드   - 신호 찾기
  hypothesis.py   가설 라운드   - 원인 가설 세우기
  plan.py         계획 라운드   - 실험 계획 + 승인 관문
  unsupported.py  평가 라운드   - 미구현 안내
  base.py         공통 토대     - 저장/취소 등 세 라운드 공유 도구
  windows.py      기간 계산     - 분석 창/기준선 창
  registry.py     단계 선택표   - phase -> 러너 객체

여기서 공개 이름과, 테스트가 monkeypatch 대상으로 쓰는 agents 모듈을 재노출한다.
"""
from __future__ import annotations

from app.agents import formatter, reviewer, workers  # noqa: F401 (재노출: 패치/사용)
from app.orchestration.phases.analysis import AnalysisRoundRunner
from app.orchestration.phases.base import (
    BasePhaseRunner,
    PhaseArtifactStore,
    PhaseRunner,
)
from app.orchestration.phases.hypothesis import HypothesisRoundRunner
from app.orchestration.phases.plan import PlanRoundRunner
from app.orchestration.phases.registry import PhaseRunnerRegistry
from app.orchestration.phases.unsupported import UnsupportedPhaseRunner
from app.orchestration.phases.windows import analysis_window, baseline_window

__all__ = [
    "AnalysisRoundRunner",
    "BasePhaseRunner",
    "HypothesisRoundRunner",
    "PhaseArtifactStore",
    "PhaseRunner",
    "PhaseRunnerRegistry",
    "PlanRoundRunner",
    "UnsupportedPhaseRunner",
    "analysis_window",
    "baseline_window",
    "formatter",
    "reviewer",
    "workers",
]
