from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from launchpilot.knowledge.contracts.search_profile import RetrievalMethod


class ChunkingMethod(StrEnum):
    WHOLE_DOCUMENT = "whole_document"
    FIXED_TOKEN = "fixed_token"
    SENTENCE = "sentence"
    RECURSIVE = "recursive"
    SEMANTIC = "semantic"


class FusionMethod(StrEnum):
    WEIGHTED_SCORE = "weighted_score"
    RRF = "rrf"


class ExperimentStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class ChunkingConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: ChunkingMethod
    version: str = Field(min_length=1)
    max_tokens: int = Field(default=400, ge=16, le=8192)
    overlap_tokens: int = Field(default=0, ge=0, le=4096)

    @model_validator(mode="after")
    def validate_overlap(self) -> ChunkingConfig:
        if self.overlap_tokens >= self.max_tokens:
            raise ValueError("overlap_tokens must be smaller than max_tokens")
        return self


class RetrievalConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: RetrievalMethod
    version: str = Field(min_length=1)
    top_k: int = Field(default=10, ge=1, le=100)
    search_scope: str = Field(default="campaign", pattern=r"^(campaign|workspace)$")
    provider: str | None = None
    fusion: FusionMethod | None = None
    alpha: float | None = Field(default=None, ge=0.0, le=1.0)
    rrf_k: int = Field(default=60, ge=1, le=1000)
    reranker: str | None = None

    @model_validator(mode="after")
    def validate_hybrid_options(self) -> RetrievalConfig:
        if self.method == RetrievalMethod.HYBRID:
            if self.fusion is None:
                raise ValueError("hybrid retrieval requires fusion")
            if self.fusion == FusionMethod.WEIGHTED_SCORE and self.alpha is None:
                raise ValueError("weighted hybrid retrieval requires alpha")
        elif self.fusion is not None or self.alpha is not None:
            raise ValueError("fusion and alpha are only valid for hybrid retrieval")
        return self


class ExperimentManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    execution_id: UUID = Field(default_factory=uuid4)
    experiment_id: UUID = Field(default_factory=uuid4)
    matrix_version: str = Field(min_length=1)
    golden_version: str = Field(min_length=1)
    corpus_version: str = Field(min_length=1)
    split: str = Field(pattern=r"^(tune|validation|holdout)$")
    chunker: ChunkingConfig
    retriever: RetrievalConfig
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvaluationDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_ref: str = Field(min_length=1)
    text: str = Field(min_length=1)
    title: str = ""
    campaign_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GoldEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_ref: str = Field(min_length=1)
    relevance: int = Field(default=3, ge=1, le=3)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_span(self) -> GoldEvidence:
        if (self.char_start is None) != (self.char_end is None):
            raise ValueError("char_start and char_end must be supplied together")
        if self.char_start is not None and self.char_end <= self.char_start:
            raise ValueError("char_end must be greater than char_start")
        return self


class EvaluationCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    query_profile: str = Field(min_length=1)
    split: str = Field(pattern=r"^(tune|validation|holdout)$")
    campaign_ref: str | None = None
    evidence: tuple[GoldEvidence, ...] = Field(min_length=1)
    taxonomy: dict[str, str | list[str]] = Field(default_factory=dict)


class Chunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk_id: str = Field(min_length=1)
    document_ref: str = Field(min_length=1)
    text: str = Field(min_length=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScoredChunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk: Chunk
    score: float
    rank: int = Field(ge=1)
    component_scores: dict[str, float] = Field(default_factory=dict)


class CaseMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    recall_at_k: float = Field(ge=0.0, le=1.0)
    reciprocal_rank: float = Field(ge=0.0, le=1.0)
    ndcg_at_k: float = Field(ge=0.0, le=1.0)
    context_precision_at_k: float = Field(ge=0.0, le=1.0)


class ExperimentCaseResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str
    query_profile: str
    taxonomy: dict[str, str | list[str]]
    latency_ms: float = Field(ge=0.0)
    retrieved: tuple[ScoredChunk, ...]
    metrics: CaseMetrics


class SliceMetric(BaseModel):
    model_config = ConfigDict(frozen=True)

    dimension: str
    value: str
    metric_name: str
    metric_value: float
    sample_size: int = Field(ge=1)


class ExperimentResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    manifest: ExperimentManifest
    status: ExperimentStatus
    started_at: datetime
    finished_at: datetime
    block_reason: str | None = None
    document_count: int = Field(default=0, ge=0)
    chunk_count: int = Field(default=0, ge=0)
    eligible_case_count: int = Field(default=0, ge=0)
    aggregate_metrics: dict[str, float] = Field(default_factory=dict)
    slice_metrics: tuple[SliceMetric, ...] = ()
    case_results: tuple[ExperimentCaseResult, ...] = ()
