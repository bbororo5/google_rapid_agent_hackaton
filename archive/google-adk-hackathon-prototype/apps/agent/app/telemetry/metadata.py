"""Public metadata builders for the Agent Core telemetry component."""

from __future__ import annotations

from typing import Any

from app.telemetry.keys import TelemetryKey

TelemetryMetadata = dict[str, Any]


def turn_metadata(
    *,
    thread_id: str,
    workspace_id: str | None,
    campaign_id: str | None,
    stage: str = "TURN",
) -> TelemetryMetadata:
    """Build the base metadata shared by one accepted user turn."""
    return {
        TelemetryKey.THREAD_ID.value: thread_id,
        TelemetryKey.WORKSPACE_ID.value: workspace_id,
        TelemetryKey.CAMPAIGN_ID.value: campaign_id,
        TelemetryKey.STAGE.value: stage,
    }


def trace_metadata(
    *,
    request_id: str,
    trace_id: str,
    trace_source: str,
    thread_id: str,
    workspace_id: str | None,
    campaign_id: str | None,
    otel_trace_id: str | None = None,
) -> TelemetryMetadata:
    """Build metadata that links Java trace context to Agent Core telemetry."""
    metadata = {
        TelemetryKey.REQUEST_ID.value: request_id,
        TelemetryKey.TRACE_ID.value: trace_id,
        TelemetryKey.TRACE_SOURCE.value: trace_source,
        TelemetryKey.THREAD_ID.value: thread_id,
        TelemetryKey.WORKSPACE_ID.value: workspace_id,
        TelemetryKey.CAMPAIGN_ID.value: campaign_id,
    }
    if otel_trace_id:
        metadata[TelemetryKey.OTEL_TRACE_ID.value] = otel_trace_id
    return metadata


def decision_metadata(
    *,
    revision_before: int,
    revision_after: int,
    intent: str,
    response_mode: str,
    reducer_decision: str,
    delegation_mode: str,
    phase: str,
) -> TelemetryMetadata:
    """Build metadata for the orchestrator's reducer/delegation decision."""
    return {
        TelemetryKey.AGENT_STATE_REVISION_BEFORE.value: revision_before,
        TelemetryKey.AGENT_STATE_REVISION_AFTER.value: revision_after,
        TelemetryKey.AGENT_DELTA_INTENT.value: intent,
        TelemetryKey.AGENT_DELTA_RESPONSE_MODE.value: response_mode,
        TelemetryKey.AGENT_REDUCER_DECISION.value: reducer_decision,
        TelemetryKey.AGENT_DELEGATION_MODE.value: delegation_mode,
        TelemetryKey.PHASE.value: phase,
    }


def guardrail_metadata(
    *,
    thread_id: str,
    workspace_id: str | None,
    campaign_id: str | None,
    validator_passed: bool | None = None,
    backtrack_count: int = 0,
) -> TelemetryMetadata:
    """Build metadata for reviewer/eval guardrail spans."""
    return {
        TelemetryKey.THREAD_ID.value: thread_id,
        TelemetryKey.WORKSPACE_ID.value: workspace_id,
        TelemetryKey.CAMPAIGN_ID.value: campaign_id,
        TelemetryKey.VALIDATOR_PASSED.value: validator_passed,
        TelemetryKey.BACKTRACK_COUNT.value: backtrack_count,
    }


def goal_metadata(
    *,
    kind: str,
    budget_profile: str,
    max_steps: int,
    max_llm_calls: int,
) -> TelemetryMetadata:
    """Build metadata for the active orchestration goal and budget."""
    return {
        TelemetryKey.AGENT_GOAL_KIND.value: kind,
        TelemetryKey.AGENT_GOAL_BUDGET_PROFILE.value: budget_profile,
        TelemetryKey.AGENT_GOAL_MAX_STEPS.value: max_steps,
        TelemetryKey.AGENT_GOAL_MAX_LLM_CALLS.value: max_llm_calls,
    }


def scope_metadata(
    *,
    workspace_id: str | None,
    campaign_id: str | None,
) -> TelemetryMetadata:
    """Build metadata for the active tenant/campaign scope."""
    return {
        TelemetryKey.AGENT_SCOPE_WORKSPACE_ID.value: workspace_id,
        TelemetryKey.AGENT_SCOPE_CAMPAIGN_ID.value: campaign_id,
    }


def repository_metadata(
    *,
    backend: str | None = None,
    conflict: bool | None = None,
) -> TelemetryMetadata:
    """Build metadata for state repository interactions."""
    metadata: TelemetryMetadata = {}
    if backend is not None:
        metadata[TelemetryKey.AGENT_REPOSITORY_BACKEND.value] = backend
    if conflict is not None:
        metadata[TelemetryKey.AGENT_REPOSITORY_CONFLICT.value] = conflict
    return metadata


def state_delta_metadata(delta_id: str) -> TelemetryMetadata:
    """Build metadata for a persisted state-delta event."""
    return {TelemetryKey.AGENT_STATE_DELTA_ID.value: delta_id}


def episode_metadata(*, episode_id: str, outcome: str) -> TelemetryMetadata:
    """Build metadata for a stored episode checkpoint."""
    return {
        TelemetryKey.AGENT_EPISODE_ID.value: episode_id,
        TelemetryKey.AGENT_EPISODE_OUTCOME.value: outcome,
    }


def evidence_metadata(*, evidence_ref_count: int) -> TelemetryMetadata:
    """Build metadata for summarized evidence lookup output."""
    return {TelemetryKey.EVIDENCE_REF_COUNT.value: evidence_ref_count}
