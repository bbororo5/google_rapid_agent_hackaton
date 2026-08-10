from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any, Protocol

from langchain_core.messages import ToolMessage

from launchpilot.application.analysis import AgentEvidenceRef

from .models import AnalysisTranscript


class EvidenceDecoder(Protocol):
    def decode(self, payload: dict[str, Any]) -> tuple[AgentEvidenceRef, ...]: ...


class MetricEvidenceDecoder:
    def decode(self, payload: dict[str, Any]) -> tuple[AgentEvidenceRef, ...]:
        return tuple(
            AgentEvidenceRef(
                kind="METRIC",
                observation_id=metric["observation_id"],
                surface=metric["surface"],
                metric_key=metric["metric_key"],
                source_ref=metric["provenance_ref"],
                captured_at=metric["captured_at"],
            )
            for metric in payload.get("metrics", [])
        )


class DocumentEvidenceDecoder:
    _required_fields = frozenset({"id", "source_ref", "content", "created_at"})

    def decode(self, payload: dict[str, Any]) -> tuple[AgentEvidenceRef, ...]:
        if not self._required_fields <= payload.keys():
            return ()
        return (
            AgentEvidenceRef(
                kind="DOCUMENT",
                document_id=payload["id"],
                source_ref=payload["source_ref"],
                captured_at=payload["created_at"],
            ),
        )


class EvidenceCollector:
    """Delegates each tool-result message shape to evidence decoder objects."""

    def __init__(self, decoders: tuple[EvidenceDecoder, ...] | None = None) -> None:
        self._decoders = decoders or (
            MetricEvidenceDecoder(),
            DocumentEvidenceDecoder(),
        )

    def collect(self, transcript: AnalysisTranscript) -> tuple[AgentEvidenceRef, ...]:
        evidence: dict[tuple[str, str], AgentEvidenceRef] = {}
        for payload in self._tool_payloads(transcript):
            for decoder in self._decoders:
                for item in decoder.decode(payload):
                    evidence[(item.kind, item.source_ref)] = item
        return tuple(evidence.values())

    def _tool_payloads(
        self, transcript: AnalysisTranscript
    ) -> Iterable[dict[str, Any]]:
        for message in transcript.messages:
            if not isinstance(message, ToolMessage):
                continue
            try:
                payload = json.loads(str(message.content))
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                yield payload
