from __future__ import annotations

from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator


class CampaignSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    name: str
    goal: str
    period_start: date
    period_end: date
    target_metrics: tuple[str, ...]


class MetricEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    observation_id: UUID
    captured_at: datetime
    completeness_status: str
    missing_reasons: tuple[str, ...]
    surface: str
    connector: str
    account_ref: str
    external_campaign_ref: str | None
    subject_ref: str
    subject_level: str
    metric_key: str
    value: float
    unit: str
    period_start: date
    period_end: date
    provenance_ref: str
    calculation: str | None


class CampaignPerformance(BaseModel):
    model_config = ConfigDict(frozen=True)

    campaign: CampaignSummary
    metrics: tuple[MetricEvidence, ...]


class CampaignMetricQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    campaign_id: UUID
    workspace_id: UUID
    start_date: date | None = None
    end_date: date | None = None
    platforms: tuple[str, ...] = ()
    metric_keys: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_period(self) -> CampaignMetricQuery:
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("start_date and end_date must be provided together")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        return self


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
