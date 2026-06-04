"""Builds + appends contract-shaped AgentWorkflowEvents to a RunRecord.

Every event carries a monotonic `sequence` so the WS endpoint can replay.
Stage/status side effects on the record are centralized here.
"""
from __future__ import annotations

from typing import Optional

from app.contracts import (
    AgentObservation,
    AgentObservationKind,
    AgentResultPayload,
    AgentRunStage,
    AgentRunStatus,
    AgentStepSnapshot,
    AgentStepStatus,
    AgentWorkflowEvent,
    AgentWorkflowEventType,
)
from app.ids import event_id, now_iso, observation_id, step_id
from app.runtime.store import RunRecord


async def _emit(
    record: RunRecord,
    type_: AgentWorkflowEventType,
    *,
    status: Optional[AgentRunStatus] = None,
    step: Optional[AgentStepSnapshot] = None,
    observation: Optional[AgentObservation] = None,
    payload: Optional[AgentResultPayload] = None,
    error_message: Optional[str] = None,
) -> AgentWorkflowEvent:
    if status is not None:
        record.status = status
    event = AgentWorkflowEvent(
        event_id=event_id(),
        type=type_,
        agent_run_id=record.agent_run_id,
        sequence=record.next_sequence(),
        occurred_at=now_iso(),
        status=status or record.status,
        step=step,
        observation=observation,
        payload=payload,
        error_message=error_message,
    )
    await record.append_event(event)
    return event


async def run_started(record: RunRecord) -> None:
    record.started_at = now_iso()
    await _emit(record, AgentWorkflowEventType.run_started, status=AgentRunStatus.PENDING)


async def step_updated(
    record: RunRecord,
    *,
    order: int,
    stage: AgentRunStage,
    status: AgentStepStatus,
    run_status: Optional[AgentRunStatus] = None,
) -> None:
    record.current_stage = stage.value
    await _emit(
        record,
        AgentWorkflowEventType.step_updated,
        status=run_status,
        step=AgentStepSnapshot(id=step_id(), order=order, stage=stage, status=status),
    )


async def observation(
    record: RunRecord,
    *,
    kind: AgentObservationKind,
    title: str,
    summary: str,
    evidence_refs: Optional[list[str]] = None,
) -> None:
    await _emit(
        record,
        AgentWorkflowEventType.observation_created,
        observation=AgentObservation(
            id=observation_id(),
            kind=kind,
            title=title,
            summary=summary,
            evidence_refs=evidence_refs,
        ),
    )


async def signal_detected(record: RunRecord, payload: AgentResultPayload) -> None:
    await _emit(record, AgentWorkflowEventType.signal_detected, payload=payload)


async def hypothesis_created(record: RunRecord, payload: AgentResultPayload) -> None:
    await _emit(record, AgentWorkflowEventType.hypothesis_created, payload=payload)


async def experiment_plan_drafted(record: RunRecord, payload: AgentResultPayload) -> None:
    await _emit(
        record,
        AgentWorkflowEventType.experiment_plan_drafted,
        status=AgentRunStatus.WAITING_FOR_APPROVAL,
        payload=payload,
    )
    record.completed_at = now_iso()


async def run_failed(record: RunRecord, message: str) -> None:
    record.error_message = message
    record.completed_at = now_iso()
    await _emit(
        record,
        AgentWorkflowEventType.run_failed,
        status=AgentRunStatus.FAILED,
        error_message=message,
    )


async def run_cancelled(record: RunRecord) -> None:
    record.cancelled = True
    record.completed_at = now_iso()
    await _emit(record, AgentWorkflowEventType.run_cancelled, status=AgentRunStatus.CANCELLED)
