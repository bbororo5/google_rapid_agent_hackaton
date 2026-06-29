"""LaunchPilot telemetry facade.

Domain code should describe what happened in LaunchPilot terms; this package
translates those events into the OpenInference/OpenTelemetry spans implemented
by ``app.tracing``.
"""

from app.telemetry.service import (  # noqa: F401
    evidence_span,
    guardrail_span,
    pipeline_span,
    record_evidence_result,
    record_episode_checkpoint,
    record_guardrail_result,
    record_pipeline_outcome,
    record_repository_conflict,
    record_state_delta,
    record_turn_decision,
    record_turn_outcome,
    turn_span,
)
from app.telemetry.keys import TelemetryKey  # noqa: F401
from app.telemetry.metadata import (  # noqa: F401
    TelemetryMetadata,
    decision_metadata,
    episode_metadata,
    evidence_metadata,
    goal_metadata,
    guardrail_metadata,
    repository_metadata,
    state_delta_metadata,
    trace_metadata,
    turn_metadata,
)
from app.telemetry.trace_context import AgentTraceContext  # noqa: F401

__all__ = [
    "AgentTraceContext",
    "TelemetryKey",
    "TelemetryMetadata",
    "decision_metadata",
    "episode_metadata",
    "evidence_metadata",
    "evidence_span",
    "goal_metadata",
    "guardrail_metadata",
    "guardrail_span",
    "pipeline_span",
    "record_evidence_result",
    "record_episode_checkpoint",
    "record_guardrail_result",
    "record_pipeline_outcome",
    "record_repository_conflict",
    "record_state_delta",
    "record_turn_decision",
    "record_turn_outcome",
    "repository_metadata",
    "state_delta_metadata",
    "trace_metadata",
    "turn_metadata",
    "turn_span",
]
