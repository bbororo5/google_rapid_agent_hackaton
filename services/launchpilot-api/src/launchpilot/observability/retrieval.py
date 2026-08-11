from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.trace import Span, Tracer

from launchpilot.knowledge.public import RetrievalProfile, RetrievalSearchObservation


class _OpenTelemetryRetrievalSearchObservation:
    def __init__(self, span: Span) -> None:
        self._span = span

    def returned(self, count: int) -> None:
        self._span.set_attribute("launchpilot.retrieval.returned_count", count)


class OpenTelemetryRetrievalObserver:
    """Translate retrieval events into OpenTelemetry spans at the system boundary."""

    def __init__(self, tracer: Tracer | None = None) -> None:
        self._tracer = tracer or trace.get_tracer(__name__)

    @contextmanager
    def observe_search(
        self,
        *,
        profile: RetrievalProfile,
        query_length: int,
        document_type_filter_count: int,
        top_k: int,
    ) -> Iterator[RetrievalSearchObservation]:
        with self._tracer.start_as_current_span(
            "launchpilot.retrieval.text.search"
        ) as span:
            span.set_attribute("launchpilot.retrieval.method", profile.method)
            span.set_attribute(
                "launchpilot.retrieval.index_version", profile.index_version
            )
            span.set_attribute(
                "launchpilot.retrieval.chunker_version", profile.chunker_version
            )
            span.set_attribute(
                "launchpilot.retrieval.retriever_version",
                profile.retriever_version,
            )
            span.set_attribute("launchpilot.retrieval.top_k", top_k)
            span.set_attribute("launchpilot.retrieval.query_length", query_length)
            span.set_attribute(
                "launchpilot.retrieval.document_type_filter_count",
                document_type_filter_count,
            )
            yield _OpenTelemetryRetrievalSearchObservation(span)
