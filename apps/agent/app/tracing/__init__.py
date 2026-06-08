"""Domain span helpers (contract 06-observability).

`app/observability.py` registers the Phoenix exporter + ADK auto-instrumentation
(LLM/TOOL spans). This package adds the LaunchPilot *domain* spans the contract
requires on top of that: AGENT / CHAIN / RETRIEVER / GUARDRAIL / EVALUATOR.

All helpers are no-ops when tracing is off (no provider registered), so the
golden path and offline/stub runs are unaffected.
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
