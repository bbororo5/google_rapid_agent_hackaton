from __future__ import annotations

from typing import Protocol

from .contracts.retrieval import CampaignMetricQuery, CampaignPerformance


class StructuredRetrievalRepository(Protocol):
    def get_campaign_performance(
        self, query: CampaignMetricQuery
    ) -> CampaignPerformance | None: ...


class StructuredRetrievalService:
    """Deterministic campaign retrieval, independent from LLM orchestration."""

    def __init__(self, repository: StructuredRetrievalRepository) -> None:
        self._repository = repository

    def get_campaign_performance(
        self, query: CampaignMetricQuery
    ) -> CampaignPerformance | None:
        return self._repository.get_campaign_performance(query)
