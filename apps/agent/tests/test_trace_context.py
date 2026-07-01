from __future__ import annotations

import logging
from types import SimpleNamespace

from app.infra_observability import CorrelationLogFilter
from app.telemetry import AgentTraceContext


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


def test_agent_trace_context_maps_java_turn_trace() -> None:
    turn = SimpleNamespace(
        thread_id="thread_1",
        workspace_id="workspace_1",
        campaign_id="campaign_1",
        trace_context=SimpleNamespace(
            request_id="req_cmd_1",
            source="java-backend",
            otel_trace_id="0123456789abcdef0123456789abcdef",
        ),
    )

    trace = AgentTraceContext.from_turn(turn)

    assert trace.request_id == "req_cmd_1"
    assert trace.source == "java-backend"
    assert trace.log_trace_id == "0123456789abcdef0123456789abcdef"
    assert trace.metadata(
        thread_id=turn.thread_id,
        workspace_id=turn.workspace_id,
        campaign_id=turn.campaign_id,
    ) == {
        "request_id": "req_cmd_1",
        "trace_id": "0123456789abcdef0123456789abcdef",
        "trace_source": "java-backend",
        "thread_id": "thread_1",
        "workspace_id": "workspace_1",
        "campaign_id": "campaign_1",
        "otel_trace_id": "0123456789abcdef0123456789abcdef",
    }


def test_agent_trace_context_binds_log_correlation() -> None:
    trace = AgentTraceContext(
        request_id="req_cmd_1",
        source="java-backend",
        otel_trace_id="0123456789abcdef0123456789abcdef",
    )
    record = _record()

    with trace.bind_logs(thread_id="thread_1", workspace_id="workspace_1", campaign_id="campaign_1"):
        assert CorrelationLogFilter().filter(record)

    assert record.request_id == "req_cmd_1"
    assert record.trace_id == "0123456789abcdef0123456789abcdef"
    assert record.thread_id == "thread_1"
    assert record.workspace_id == "workspace_1"
    assert record.campaign_id == "campaign_1"
