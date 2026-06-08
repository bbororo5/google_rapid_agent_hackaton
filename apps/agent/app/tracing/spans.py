"""OpenInference domain spans for LaunchPilot (contract 06-observability).

Thin context managers over the OpenTelemetry tracer that stamp the
`openinference.span.kind` + common attributes the contract requires. When no
tracer provider is registered (Phoenix key absent) OTel returns a no-op tracer,
so every helper here is a cheap no-op offline -- the golden path never changes.

Attribute keys follow OpenInference semantic conventions so Phoenix/Arize render
them natively (span kind, input/output value, retrieval documents, metadata).

Redaction (contract 06 §Redaction): callers pass concise JSON summaries, never
raw CSV, prompts-with-secrets, API keys, or raw provider exception bodies.
"""
from __future__ import annotations

import json
from contextlib import contextmanager

try:
    from opentelemetry import trace

    _tracer = trace.get_tracer("launchpilot")
except Exception:  # pragma: no cover - opentelemetry is a hard dep, guard anyway
    _tracer = None

# --- OpenInference attribute keys ---
_KIND = "openinference.span.kind"
_IN_VALUE = "input.value"
_IN_MIME = "input.mime_type"
_OUT_VALUE = "output.value"
_OUT_MIME = "output.mime_type"
_METADATA = "metadata"
_SESSION = "session.id"


def _json(value) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001 - tracing must never raise
        return str(value)


def _mime(value) -> str:
    return "text/plain" if isinstance(value, str) else "application/json"


class _NoSpan:
    """Stand-in when tracing is unavailable; every method is a no-op."""

    def set_attribute(self, *_args, **_kwargs) -> None:  # noqa: D401
        return None


def _session_id(workspace_id, campaign_id) -> str:
    # Contract 06 §Required Trace Identity: recommended session key.
    return f"{workspace_id or '-'}:{campaign_id or '-'}"


@contextmanager
def _span(kind: str, name: str, *, input_value=None, output_value=None,
          metadata=None, workspace_id=None, campaign_id=None):
    if _tracer is None:
        yield _NoSpan()
        return
    with _tracer.start_as_current_span(name) as span:
        span.set_attribute(_KIND, kind)
        span.set_attribute(_SESSION, _session_id(workspace_id, campaign_id))
        if input_value is not None:
            span.set_attribute(_IN_VALUE, _json(input_value))
            span.set_attribute(_IN_MIME, _mime(input_value))
        if output_value is not None:
            set_output(span, output_value)
        if metadata is not None:
            span.set_attribute(_METADATA, _json(metadata))
        yield span


# --- public setters (call inside a span block; no-op safe) ---
def set_output(span, value) -> None:
    span.set_attribute(_OUT_VALUE, _json(value))
    span.set_attribute(_OUT_MIME, _mime(value))


def set_metadata(span, metadata: dict) -> None:
    span.set_attribute(_METADATA, _json(metadata))


def set_documents(span, documents: list[dict]) -> None:
    """Stamp retrieval.documents.* (contract 06 §Retriever Span Contract).

    Each doc: {id, content?, score?, metadata?}. `document.id` should match the
    EvidenceRef.ref_id that can later appear in the final payload.
    """
    for i, doc in enumerate(documents):
        base = f"retrieval.documents.{i}.document"
        span.set_attribute(f"{base}.id", str(doc.get("id", "")))
        if doc.get("content") is not None:
            span.set_attribute(f"{base}.content", _json(doc["content"]))
        if doc.get("score") is not None:
            span.set_attribute(f"{base}.score", doc["score"])
        if doc.get("metadata") is not None:
            span.set_attribute(f"{base}.metadata", _json(doc["metadata"]))


# --- typed span kinds (contract 06 §Span Hierarchy) ---
def agent_span(name: str, **kw):
    """Whole thread turn."""
    return _span("AGENT", name, **kw)


def chain_span(name: str, **kw):
    """Orchestrator pipeline / worker handoff."""
    return _span("CHAIN", name, **kw)


def retriever_span(name: str, *, tool_name: str | None = None, **kw):
    """Evidence retrieval from Elastic (wraps an Evidence tool call)."""
    cm = _span("RETRIEVER", name, **kw)
    if tool_name is not None:
        # Attach tool.name once the span is open.
        @contextmanager
        def _wrap():
            with cm as span:
                span.set_attribute("metadata.tool_name", tool_name)
                yield span
        return _wrap()
    return cm


def guardrail_span(name: str, **kw):
    """Reviewer Gate checks (deterministic validation, authoritative)."""
    return _span("GUARDRAIL", name, **kw)


def evaluator_span(name: str, **kw):
    """Deterministic validation summary OR LLM-as-a-judge quality score."""
    return _span("EVALUATOR", name, **kw)
