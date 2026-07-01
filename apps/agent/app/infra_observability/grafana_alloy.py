"""Grafana Alloy export for service-level logs, metrics, and traces."""

from __future__ import annotations

import logging

log = logging.getLogger("launchpilot.infra_observability")

_registered = False


def init_infra_observability(trace_provider) -> None:
    """Export Python service telemetry to local Alloy when OTLP is configured."""
    global _registered
    if _registered:
        return

    from app.config import get_settings

    settings = get_settings()
    if not settings.otel_endpoint:
        return

    try:
        from opentelemetry import metrics
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception as exc:  # noqa: BLE001 - telemetry must not break runtime
        log.warning("Alloy telemetry disabled: %s", exc)
        return

    endpoint = settings.otel_endpoint.rstrip("/")
    resource = Resource.create({
        "service.name": "launchpilot-agent",
        "service.namespace": "launchpilot",
        "deployment.environment": "local",
    })

    if trace_provider is not None and hasattr(trace_provider, "add_span_processor"):
        trace_provider.add_span_processor(BatchSpanProcessor(
            OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
        ))

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics"),
            export_interval_millis=15000,
        )],
    )
    metrics.set_meter_provider(meter_provider)
    meter = metrics.get_meter("launchpilot-agent")
    meter.create_counter("launchpilot.agent.startups").add(1)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(
        OTLPLogExporter(endpoint=f"{endpoint}/v1/logs")
    ))
    logging.getLogger("launchpilot").addHandler(
        LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
    )

    _registered = True
    log.info("Alloy telemetry enabled (endpoint=%s)", endpoint)
