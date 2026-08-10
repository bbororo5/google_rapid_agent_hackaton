from __future__ import annotations

import logging

from app.infra_observability import CorrelationLogFilter, bind_correlation


def _record() -> logging.LogRecord:
    return logging.LogRecord(
        name="launchpilot.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="message",
        args=(),
        exc_info=None,
    )


def test_correlation_log_filter_defaults_to_placeholders() -> None:
    record = _record()

    assert CorrelationLogFilter().filter(record)

    assert record.request_id == "-"
    assert record.trace_id == "-"
    assert record.thread_id == "-"
    assert record.workspace_id == "-"
    assert record.campaign_id == "-"


def test_bind_correlation_attaches_fields_to_log_records() -> None:
    record = _record()

    with bind_correlation(
        request_id="req_cmd_1",
        trace_id="trc_1",
        thread_id="thread_1",
        workspace_id="workspace_1",
        campaign_id="campaign_1",
    ):
        assert CorrelationLogFilter().filter(record)

    assert record.request_id == "req_cmd_1"
    assert record.trace_id == "trc_1"
    assert record.thread_id == "thread_1"
    assert record.workspace_id == "workspace_1"
    assert record.campaign_id == "campaign_1"


def test_bind_correlation_restores_previous_context() -> None:
    outer = _record()
    inner = _record()
    restored = _record()
    filter_ = CorrelationLogFilter()

    with bind_correlation(request_id="req_outer", thread_id="thread_outer"):
        assert filter_.filter(outer)
        with bind_correlation(request_id="req_inner", thread_id="thread_inner"):
            assert filter_.filter(inner)
        assert filter_.filter(restored)

    assert outer.request_id == "req_outer"
    assert inner.request_id == "req_inner"
    assert restored.request_id == "req_outer"
    assert restored.thread_id == "thread_outer"
