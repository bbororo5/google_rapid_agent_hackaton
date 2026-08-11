from uuid import uuid4

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from launchpilot.knowledge import TextRetrievalService
from launchpilot.observability.retrieval import OpenTelemetryRetrievalObserver


class EmptyDocumentSearch:
    def search(self, **kwargs):
        return ()


def test_text_retrieval_emits_versioned_span_without_raw_query() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    service = TextRetrievalService(
        repository=object(),  # type: ignore[arg-type]
        search=EmptyDocumentSearch(),  # type: ignore[arg-type]
        observer=OpenTelemetryRetrievalObserver(
            provider.get_tracer("test-retrieval")
        ),
    )

    service.search(
        workspace_id=uuid4(),
        campaign_id=uuid4(),
        query="소재 피로 CTR 하락",
        top_k=3,
    )
    provider.shutdown()

    span = exporter.get_finished_spans()[0]
    attributes = span.attributes or {}
    assert span.name == "launchpilot.retrieval.text.search"
    assert attributes["launchpilot.retrieval.method"] == "bm25"
    assert attributes["launchpilot.retrieval.index_version"] == (
        "campaign-documents-v1"
    )
    assert attributes["launchpilot.retrieval.chunker_version"] == (
        "whole-document-v1"
    )
    assert attributes["launchpilot.retrieval.retriever_version"] == "bm25-v1"
    assert attributes["launchpilot.retrieval.top_k"] == 3
    assert attributes["launchpilot.retrieval.returned_count"] == 0
    assert "launchpilot.retrieval.query" not in attributes
