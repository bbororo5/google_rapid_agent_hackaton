"""Golden path end-to-end in STUB mode (no LLM, no Elastic).

Drives the orchestrator like the API would and asserts the run reaches
WAITING_FOR_APPROVAL with a contract-valid payload and contract-valid events.
"""
from __future__ import annotations

import pytest

from app import orchestrator
from app.contracts import (
    AgentRunStatus,
    AgentWorkflowEvent,
    AgentWorkflowEventType,
    DateRange,
    InternalAgentRunRequest,
    TraceContext,
)
from app.runtime.store import RunStore


def _request() -> InternalAgentRunRequest:
    return InternalAgentRunRequest(
        agent_run_id="run_test123",
        workspace_id="demo_workspace",
        campaign_id="camp_comeback_teaser",
        question="What should we test next week?",
        date_range=DateRange(start="2026-05-25", end="2026-05-31"),
        trace_context=TraceContext(request_id="req_abc", source="java-backend"),
    )


@pytest.mark.asyncio
async def test_golden_path_reaches_approval() -> None:
    store = RunStore()
    record = store.create(_request())

    await orchestrator.execute(record)

    assert record.status == AgentRunStatus.WAITING_FOR_APPROVAL
    assert record.validator_passed is True
    assert record.payload is not None
    assert record.payload.signals
    assert record.payload.hypotheses
    assert record.payload.experiment_plan.items

    # Every emitted event is contract-valid and sequence is monotonic.
    seqs = [e.sequence for e in record.events]
    assert seqs == list(range(1, len(seqs) + 1))
    for e in record.events:
        AgentWorkflowEvent.model_validate(e.model_dump(mode="json"))

    types = {e.type for e in record.events}
    assert AgentWorkflowEventType.run_started in types
    assert AgentWorkflowEventType.experiment_plan_drafted in types

    # The final event carries the full payload and the approval status.
    final = record.events[-1]
    assert final.type == AgentWorkflowEventType.experiment_plan_drafted
    assert final.status == AgentRunStatus.WAITING_FOR_APPROVAL
    assert final.payload is not None


@pytest.mark.asyncio
async def test_snapshot_is_contract_valid() -> None:
    store = RunStore()
    record = store.create(_request())
    await orchestrator.execute(record)
    snap = record.snapshot()
    assert snap.status == AgentRunStatus.WAITING_FOR_APPROVAL
    assert snap.agent_diagnostics.validator_passed is True
