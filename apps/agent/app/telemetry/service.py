"""Meaning-first telemetry helpers for LaunchPilot Agent Core.

This module is the small adapter between domain events and the tracing backend:
domain code calls ``telemetry.*`` in LaunchPilot terms, while this layer maps
those calls to OpenInference/OpenTelemetry spans.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any

from app import tracing
from app.telemetry.keys import TelemetryKey
from app.telemetry.metadata import (
    episode_metadata,
    evidence_metadata,
    goal_metadata,
    guardrail_metadata,
    repository_metadata,
    scope_metadata,
    state_delta_metadata,
)


def turn_span(
    content: str,
    *,
    metadata: dict[str, Any],
    workspace_id: str | None,
    campaign_id: str | None,
) -> AbstractContextManager:
    """Start the top-level span for one user turn."""
    return tracing.agent_span(
        "launchpilot.thread",
        input_value=content[:2000],
        metadata=metadata,
        workspace_id=workspace_id,
        campaign_id=campaign_id,
    )


def pipeline_span(
    content: str,
    *,
    metadata: dict[str, Any],
    workspace_id: str | None,
    campaign_id: str | None,
) -> AbstractContextManager:
    """Start the phase execution pipeline span."""
    return tracing.chain_span(
        "launchpilot.orchestrator",
        input_value=content[:2000],
        metadata={**metadata, TelemetryKey.STAGE.value: "PIPELINE"},
        workspace_id=workspace_id,
        campaign_id=campaign_id,
    )


def evidence_span(
    span_name: str,
    *,
    tool_name: str,
    input_value: dict[str, Any],
) -> AbstractContextManager:
    """Start a retriever span for one evidence lookup."""
    return tracing.retriever_span(span_name, tool_name=tool_name, input_value=input_value)


def guardrail_span(
    *,
    input_value: dict[str, Any],
    metadata: dict[str, Any],
    workspace_id: str | None,
    campaign_id: str | None,
) -> AbstractContextManager:
    """Start the experiment-plan reviewer gate span."""
    return tracing.guardrail_span(
        "launchpilot.reviewer_gate",
        input_value=input_value,
        metadata=metadata,
        workspace_id=workspace_id,
        campaign_id=campaign_id,
    )


def record_turn_decision(
    span,
    *,
    turn_metadata: dict[str, Any],
    decision_metadata: dict[str, Any],
    workspace_id: str | None,
    campaign_id: str | None,
    repository_backend: str,
    goal,
) -> None:
    """Attach the interpreted decision and goal budget to the turn span."""
    tracing.set_metadata(
        span,
        {
            **turn_metadata,
            **scope_metadata(workspace_id=workspace_id, campaign_id=campaign_id),
            **repository_metadata(backend=repository_backend),
            **decision_metadata,
            **goal_metadata(
                kind=goal.kind.value,
                budget_profile=goal.budget_profile.value,
                max_steps=goal.budgets.max_steps,
                max_llm_calls=goal.budgets.max_llm_calls,
            ),
        },
    )


def record_turn_outcome(span, outcome: dict[str, Any]) -> None:
    """Attach the final turn outcome summary to the turn span."""
    tracing.set_output(span, outcome)


def record_pipeline_outcome(span, outcome: dict[str, Any]) -> None:
    """Attach the phase pipeline outcome summary."""
    tracing.set_output(span, outcome)


def record_evidence_result(span, result: dict[str, Any]) -> None:
    """Attach evidence lookup output without dumping raw retrieved rows."""
    refs = result.get("evidence_refs") or []
    tracing.set_documents(span, [{"id": ref} for ref in refs])
    summary = {key: value for key, value in result.items() if key != "evidence_refs"}
    summary.update(evidence_metadata(evidence_ref_count=len(refs)))
    tracing.set_output(span, summary)


def record_guardrail_result(span, report, metadata: dict[str, Any]) -> None:
    """Attach reviewer gate result metadata and validation output."""
    tracing.set_output(span, report.model_dump(mode="json"))
    tracing.set_metadata(
        span,
        {
            **metadata,
            **guardrail_metadata(
                thread_id=metadata[TelemetryKey.THREAD_ID.value],
                workspace_id=metadata[TelemetryKey.WORKSPACE_ID.value],
                campaign_id=metadata[TelemetryKey.CAMPAIGN_ID.value],
                validator_passed=report.passed,
                backtrack_count=0,
            ),
        },
    )


def record_state_delta(span, delta_id: str) -> None:
    """Attach the persisted state-delta id to the active turn span."""
    tracing.set_metadata(span, state_delta_metadata(delta_id))


def record_episode_checkpoint(span, *, episode_id: str, outcome: str) -> None:
    """Attach the saved episode checkpoint identity to the active turn span."""
    tracing.set_metadata(span, episode_metadata(episode_id=episode_id, outcome=outcome))


def record_repository_conflict(span) -> None:
    """Mark the active turn span as failed by optimistic concurrency conflict."""
    tracing.set_metadata(span, repository_metadata(conflict=True))
