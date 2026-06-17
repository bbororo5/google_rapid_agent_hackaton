"""분석 기간 계산.

분석 창(최근 7일)과 비교 기준선 창(그 직전 28일)을 날짜로 만든다.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.contracts import DateRange


def analysis_window() -> DateRange:
    # 오늘부터 6일 전까지 (총 7일).
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=6)
    return DateRange(start=start.isoformat(), end=end.isoformat())


def baseline_window(current: DateRange) -> DateRange:
    # 분석 창 시작 바로 전날부터 거슬러 28일.
    cur_start = date.fromisoformat(current.start)
    return DateRange(
        start=(cur_start - timedelta(days=28)).isoformat(),
        end=(cur_start - timedelta(days=1)).isoformat(),
    )
