from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from launchpilot.campaigns.contracts.access import CampaignScope

from .contracts.campaign_analysis import CampaignAnalysisResult
from .contracts.runtime import AnalysisWorkflow, EvidenceReader
from .evidence import EvidenceCollector
from .graph import AnalysisGraph
from .ports import CampaignDocumentReader, CampaignPerformanceReader
from .scope import ExecutionScope
from .tools import CampaignToolset


class CampaignAgent:
    def __init__(
        self, *, graph: AnalysisWorkflow, evidence_collector: EvidenceReader
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
        execution_scope = ExecutionScope.create(
            workspace_id=scope.workspace_id,
            campaign_id=scope.campaign_id,
        )
        return CampaignAgent(
            graph=AnalysisGraph(
                model_with_tools=self._model.bind_tools(tools),
                tools=tools,
                scope=execution_scope,
            ),
            evidence_collector=EvidenceCollector(),
        )
