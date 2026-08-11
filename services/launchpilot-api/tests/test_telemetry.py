from dataclasses import replace

import pytest
from fastapi import FastAPI
from langchain_core.runnables import RunnableLambda
from openinference.instrumentation.langchain import LangChainInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from launchpilot.bootstrap.config import Settings
from launchpilot.observability.runtime import TelemetryRuntime


def test_telemetry_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEMETRY_ENABLED", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    settings = Settings.from_environment()
    runtime = TelemetryRuntime(settings)

    runtime.start(FastAPI())
    runtime.shutdown()

    assert runtime.enabled is False


def test_enabled_telemetry_requires_an_otlp_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    settings = replace(
        Settings.from_environment(),
        telemetry_enabled=True,
        otel_exporter_endpoint=None,
    )

    with pytest.raises(RuntimeError, match="OTEL_EXPORTER_OTLP_ENDPOINT"):
        TelemetryRuntime(settings).start(FastAPI())


def test_openinference_instrumentor_emits_standard_langchain_span() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    instrumentor = LangChainInstrumentor()
    instrumentor.instrument(tracer_provider=provider)
    try:
        assert RunnableLambda(lambda value: value + 1).invoke(1) == 2
    finally:
        instrumentor.uninstrument()
        provider.shutdown()

    span = exporter.get_finished_spans()[0]
    assert span.attributes is not None
    assert span.attributes["openinference.span.kind"] == "CHAIN"
    assert span.attributes["input.value"] == "1"
    assert span.attributes["output.value"] == "2"
