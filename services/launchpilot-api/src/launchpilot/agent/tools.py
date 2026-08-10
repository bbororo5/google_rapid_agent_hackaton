from __future__ import annotations

import json
from datetime import date
from uuid import UUID

from langchain_core.tools import BaseTool, StructuredTool

from launchpilot.application.retrieval import (
    CampaignMetricQuery,
    StructuredRetrievalService,
)
from launchpilot.application.text_retrieval import DocumentType, TextRetrievalService

from .models import AnalysisScope


class CampaignToolset:
    """Translates LLM tool messages into server-scoped application queries."""

    def __init__(
        self,
        *,
        scope: AnalysisScope,
        retrieval: StructuredRetrievalService,
        text_retrieval: TextRetrievalService,
    ) -> None:
        self._scope = scope
        self._retrieval = retrieval
        self._text_retrieval = text_retrieval

    def tools(self) -> list[BaseTool]:
        return [
            StructuredTool.from_function(
                func=self.get_campaign_performance,
                name="get_campaign_performance",
                description=(
                    "Retrieve exact stored campaign metrics and their evidence. "
                    "Supply both dates only for an exact metric period. Platform "
                    "examples are GOOGLE_ADS, META_ADS, and YOUTUBE. Leave filters "
                    "empty to retrieve all available values."
                ),
            ),
            StructuredTool.from_function(
                func=self.search_campaign_documents,
                name="search_campaign_documents",
                description=(
                    "BM25 keyword search over this campaign's memos, briefs, and "
                    "prior analyses."
                ),
            ),
            StructuredTool.from_function(
                func=self.resolve_campaign_document,
                name="resolve_campaign_document",
                description=(
                    "Resolve a BM25 hit to its authoritative PostgreSQL source "
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

    def search_campaign_documents(
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
            top_k=top_k,
        )
        return json.dumps(
            [item.model_dump(mode="json") for item in hits], ensure_ascii=False
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
