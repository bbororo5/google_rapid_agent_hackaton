from __future__ import annotations

from fastapi import FastAPI
from openinference.instrumentation.langchain import LangChainInstrumentor
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from launchpilot.config import Settings


class TelemetryRuntime:
    """One in-process OpenTelemetry pipeline for the LaunchPilot monolith."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._provider: TracerProvider | None = None
        self._app: FastAPI | None = None
        self._langchain = LangChainInstrumentor()
        self._httpx = HTTPXClientInstrumentor()
        self._psycopg = PsycopgInstrumentor()

    @property
    def enabled(self) -> bool:
        return self._settings.telemetry_enabled

    def start(self, app: FastAPI) -> None:
        if not self.enabled or self._provider is not None:
            return
        self._settings.require_telemetry_endpoint()
        provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": self._settings.otel_service_name,
                    "service.version": app.version,
                }
            )
        )
        # The exporter reads the standard OTEL endpoint and header variables.
        # With OTEL_EXPORTER_OTLP_ENDPOINT, the HTTP exporter appends /v1/traces.
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)

        self._langchain.instrument(tracer_provider=provider)
        self._httpx.instrument(tracer_provider=provider)
        self._psycopg.instrument(tracer_provider=provider)
        FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)

        self._provider = provider
        self._app = app

    def shutdown(self) -> None:
        provider = self._provider
        if provider is None:
            return
        if self._app is not None:
            FastAPIInstrumentor.uninstrument_app(self._app)
        self._psycopg.uninstrument()
        self._httpx.uninstrument()
        self._langchain.uninstrument()
        provider.force_flush()
        provider.shutdown()
        self._provider = None
        self._app = None
