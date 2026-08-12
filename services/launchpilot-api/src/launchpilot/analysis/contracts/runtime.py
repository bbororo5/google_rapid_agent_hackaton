from typing import Protocol

from ..models import AnalysisTranscript
from .campaign_analysis import AgentEvidenceRef


class AnalysisWorkflow(Protocol):
    """Executes one question through the configured agent workflow."""

    def invoke(self, question: str) -> AnalysisTranscript: ...


class EvidenceReader(Protocol):
    """Extracts cited evidence from a completed agent transcript."""

    def collect(self, transcript: AnalysisTranscript) -> tuple[AgentEvidenceRef, ...]: ...
