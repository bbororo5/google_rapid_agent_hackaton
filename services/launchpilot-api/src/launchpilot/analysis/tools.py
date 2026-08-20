from __future__ import annotations

import json
from datetime import date
from uuid import UUID

from langchain_core.tools import BaseTool, StructuredTool

from launchpilot.campaigns.contracts.access import CampaignScope
from launchpilot.knowledge.contracts.retrieval import DocumentType, TextSearchHit
from launchpilot.performance.contracts.retrieval import CampaignMetricQuery
from .ports import CampaignDocumentReader, CampaignPerformanceReader

from .graph_retriever import MarketingKnowledgeGraph
from .reranker import MarketingDomainReranker


class CampaignToolset:
    def __init__(
        self,
        *,
        scope: CampaignScope,
        retrieval: CampaignPerformanceReader,
        text_retrieval: CampaignDocumentReader,
        reranker: MarketingDomainReranker | None = None,
        graph: MarketingKnowledgeGraph | None = None,
    ) -> None:
        self._scope = scope
        self._retrieval = retrieval
        self._text_retrieval = text_retrieval
        self._reranker = reranker or MarketingDomainReranker()
        self._graph = graph

    def tools(self) -> list[BaseTool]:
        tools: list[BaseTool] = [
            StructuredTool.from_function(
                func=self.get_campaign_performance,
                name="get_campaign_performance",
                description="Retrieve campaign performance metrics over a date range for the active campaign scope.",
            ),
            StructuredTool.from_function(
                func=self.search_documents_keyword,
                name="search_documents_keyword",
                description=(
                    "BM25 keyword search over memos, briefs, and analyses. "
                    "Accepts multiple query hypotheses (queries=['query1', 'query2']) "
                    "to batch retrieve multi-angle keyword matches in 1 single call."
                ),
            ),
            StructuredTool.from_function(
                func=self.search_documents_semantic,
                name="search_documents_semantic",
                description=(
                    "Dense vector semantic search over memos, briefs, and analyses. "
                    "Accepts multiple conceptual queries (queries=['concept1', 'concept2']) "
                    "to batch retrieve multi-angle semantic concepts in 1 single call."
                ),
            ),
            StructuredTool.from_function(
                func=self.resolve_campaign_document,
                name="resolve_campaign_document",
                description="Fetch the complete full-text body of a specific campaign document by its document_id UUID.",
            ),
        ]
        if self._graph is not None:
            tools.append(
                StructuredTool.from_function(
                    func=self.traverse_campaign_graph,
                    name="traverse_campaign_graph",
                    description=(
                        "Traverse the campaign directed Causal Knowledge Graph in 1 atomic call. "
                        "Connects Brief guidelines -> Metric anomaly facts -> Operational action memos -> "
                        "Follow-up monthly performance analyses into a verified causal chain."
                    ),
                )
            )
        return tools

    def traverse_campaign_graph(
        self,
        query: str,
        campaign_identifier: str | None = None,
    ) -> str:
        if self._graph is None:
            return json.dumps({"error": "Graph engine not initialized"})
        cid = str(self._scope.campaign_id)
        if campaign_identifier:
            c_str = str(campaign_identifier).strip()
            if len(c_str) >= 32 and "-" in c_str:
                cid = c_str
            else:
                found_id = self._graph.find_campaign_id(c_str)
                if found_id:
                    cid = found_id

        chain = self._graph.traverse(campaign_id=cid, query=query)
        return json.dumps(chain.model_dump(mode="json"), ensure_ascii=False)

    def get_campaign_performance(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        platforms: list[str] | None = None,
        metric_keys: list[str] | None = None,
    ) -> str:
        result = self._retrieval.get_campaign_performance(
            CampaignMetricQuery(
                campaign_id=self._scope.campaign_id,
                workspace_id=self._scope.workspace_id,
                start_date=start_date,
                end_date=end_date,
                platforms=tuple(platforms or ()),
                metric_keys=tuple(metric_keys or ()),
            )
        )
        if result is None:
            return json.dumps({"error": "campaign not found"})
        return result.model_dump_json()

    def search_documents_keyword(
        self,
        queries: list[str] | str,
        document_types: list[DocumentType] | None = None,
        top_k: int = 5,
    ) -> str:
        query_list = [queries] if isinstance(queries, str) else queries
        combined_hits: dict[UUID, TextSearchHit] = {}

        for q in query_list:
            hits = self._text_retrieval.search(
                workspace_id=self._scope.workspace_id,
                campaign_id=self._scope.campaign_id,
                query=q,
                document_types=tuple(document_types or ()),
                top_k=max(top_k, 10),
            )
            for h in hits:
                if h.document_id not in combined_hits or h.score > combined_hits[h.document_id].score:
                    combined_hits[h.document_id] = h

        full_query = " ".join(query_list)
        reranked = self._reranker.rerank(full_query, list(combined_hits.values()))[:top_k]
        return json.dumps(
            [item.model_dump(mode="json") for item in reranked], ensure_ascii=False
        )

    def search_documents_semantic(
        self,
        queries: list[str] | str,
        document_types: list[DocumentType] | None = None,
        top_k: int = 5,
    ) -> str:
        query_list = [queries] if isinstance(queries, str) else queries
        search_fn = getattr(
            self._text_retrieval, "search_semantic", self._text_retrieval.search
        )
        combined_hits: dict[UUID, TextSearchHit] = {}

        for q in query_list:
            hits = search_fn(
                workspace_id=self._scope.workspace_id,
                campaign_id=self._scope.campaign_id,
                query=q,
                document_types=tuple(document_types or ()),
                top_k=max(top_k, 10),
            )
            for h in hits:
                if h.document_id not in combined_hits or h.score > combined_hits[h.document_id].score:
                    combined_hits[h.document_id] = h

        full_query = " ".join(query_list)
        reranked = self._reranker.rerank(full_query, list(combined_hits.values()))[:top_k]
        return json.dumps(
            [item.model_dump(mode="json") for item in reranked], ensure_ascii=False
        )

    def resolve_campaign_document(self, document_id: UUID) -> str:
        document = self._text_retrieval.resolve(
            document_id=document_id,
            workspace_id=self._scope.workspace_id,
            campaign_id=self._scope.campaign_id,
        )
        if document is None:
            return json.dumps({"error": "document not found"})
        return document.model_dump_json()
