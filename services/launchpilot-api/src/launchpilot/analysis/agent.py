from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from launchpilot.campaigns.public import CampaignScope

from .evidence import EvidenceCollector
from .graph import AnalysisGraph
from .ports import CampaignDocumentReader, CampaignPerformanceReader
from .tools import CampaignToolset
from .use_case import CampaignAnalysisResult


class CampaignAgent:
    def __init__(
        self, *, graph: AnalysisGraph, evidence_collector: EvidenceCollector
    ) -> None:
        self._graph = graph
        self._evidence_collector = evidence_collector

    def answer(self, question: str) -> CampaignAnalysisResult:
        transcript = self._graph.invoke(question)
        return CampaignAnalysisResult(
            answer=transcript.final_answer(),
            evidence=self._evidence_collector.collect(transcript),
        )


class CampaignAgentFactory:
    """Composition object that creates one scope-bound agent per request."""

    def __init__(
        self,
        *,
        model: BaseChatModel,
        retrieval: CampaignPerformanceReader,
        text_retrieval: CampaignDocumentReader,
    ) -> None:
        self._model = model
        self._retrieval = retrieval
        self._text_retrieval = text_retrieval

    def create(self, scope: CampaignScope) -> CampaignAgent:
        toolset = CampaignToolset(
            scope=scope,
            retrieval=self._retrieval,
            text_retrieval=self._text_retrieval,
        )
        tools = toolset.tools()
        return CampaignAgent(
            graph=AnalysisGraph(
                model_with_tools=self._model.bind_tools(tools),
                tools=tools,
            ),
            evidence_collector=EvidenceCollector(),
        )
