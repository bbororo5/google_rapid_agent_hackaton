"""Domain span helpers for the Observability component.

`app.phoenix_export` registers Phoenix/OpenInference tracing and
`app.infra_observability` wires service telemetry to Alloy. This package adds
the LaunchPilot domain spans on top: AGENT / CHAIN / RETRIEVER / GUARDRAIL /
EVALUATOR.

All helpers are no-ops when tracing is off (no provider registered).
"""
from app.tracing.spans import (  # noqa: F401
    agent_span,
    chain_span,
    evaluator_span,
    guardrail_span,
    retriever_span,
    set_documents,
    set_metadata,
    set_output,
)
