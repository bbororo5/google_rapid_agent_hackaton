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
