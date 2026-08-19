from __future__ import annotations

import json
from datetime import date
from uuid import UUID

from langchain_core.tools import BaseTool, StructuredTool

from launchpilot.campaigns.contracts.access import CampaignScope
from launchpilot.knowledge.contracts.retrieval import DocumentType
from launchpilot.performance.contracts.retrieval import CampaignMetricQuery

from .ports import CampaignDocumentReader, CampaignPerformanceReader
from .reranker import MarketingDomainReranker


class CampaignToolset:
    """Translates LLM tool messages into server-scoped application queries."""

    def __init__(
        self,
        *,
        scope: CampaignScope,
        retrieval: CampaignPerformanceReader,
        text_retrieval: CampaignDocumentReader,
        reranker: MarketingDomainReranker | None = None,
    ) -> None:
        self._scope = scope
        self._retrieval = retrieval
        self._text_retrieval = text_retrieval
        self._reranker = reranker or MarketingDomainReranker()

    def tools(self) -> list[BaseTool]:
        return [
            StructuredTool.from_function(
                func=self.get_campaign_performance,
                name="get_campaign_performance",
                description=(
                    "Retrieve exact stored campaign metrics and their evidence from PostgreSQL. "
                    "Supply both dates only for an exact metric period. Platform "
                    "examples are GOOGLE_ADS, META_ADS, and YOUTUBE. Leave filters "
                    "empty to retrieve all available values."
                ),
            ),
            StructuredTool.from_function(
                func=self.search_documents_keyword,
                name="search_documents_keyword",
                description=(
                    "BM25 keyword search over this campaign's memos, briefs, and "
                    "prior analyses. Best for exact campaign codes (e.g. C0010), "
                    "product names, metrics, and specific technical terminology."
                ),
            ),
            StructuredTool.from_function(
                func=self.search_documents_semantic,
                name="search_documents_semantic",
                description=(
                    "Dense vector semantic search over this campaign's memos, briefs, and "
                    "prior analyses. Best for conceptual questions, marketing jargon, "
                    "creative fatigue reasons, and conversational inquiries."
                ),
            ),
            StructuredTool.from_function(
                func=self.search_campaign_documents,
                name="search_campaign_documents",
                description=(
                    "BM25 keyword search over this campaign's memos, briefs, and "
                    "prior analyses (alias for search_documents_keyword)."
                ),
            ),
            StructuredTool.from_function(
                func=self.resolve_campaign_document,
                name="resolve_campaign_document",
                description=(
                    "Resolve a document hit to its authoritative PostgreSQL source "
                    "document before using it as evidence."
                ),
            ),
        ]

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
        query: str,
        document_types: list[DocumentType] | None = None,
        top_k: int = 5,
    ) -> str:
        hits = self._text_retrieval.search(
            workspace_id=self._scope.workspace_id,
            campaign_id=self._scope.campaign_id,
            query=query,
            document_types=tuple(document_types or ()),
            top_k=max(top_k, 10),
        )
        reranked = self._reranker.rerank(query, hits)[:top_k]
        return json.dumps(
            [item.model_dump(mode="json") for item in reranked], ensure_ascii=False
        )

    def search_documents_semantic(
        self,
        query: str,
        document_types: list[DocumentType] | None = None,
        top_k: int = 5,
    ) -> str:
        search_fn = getattr(
            self._text_retrieval, "search_semantic", self._text_retrieval.search
        )
        hits = search_fn(
            workspace_id=self._scope.workspace_id,
            campaign_id=self._scope.campaign_id,
            query=query,
            document_types=tuple(document_types or ()),
            top_k=max(top_k, 10),
        )
        reranked = self._reranker.rerank(query, hits)[:top_k]
        return json.dumps(
            [item.model_dump(mode="json") for item in reranked], ensure_ascii=False
        )

    def search_campaign_documents(
        self,
        query: str,
        document_types: list[DocumentType] | None = None,
        top_k: int = 5,
    ) -> str:
        return self.search_documents_keyword(
            query=query,
            document_types=document_types,
            top_k=top_k,
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
