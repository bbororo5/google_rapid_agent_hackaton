from __future__ import annotations

from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from launchpilot.evaluation.contracts import ExpectedBehavior


class JudgeVerdict(StrEnum):
    ENTAILED = "entailed"
    PARTIALLY_ENTAILED = "partially_entailed"
    NOT_ENTAILED = "not_entailed"
    CONTRADICTED = "contradicted"
    INDETERMINATE = "indeterminate"


class ClaimSupport(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    INDETERMINATE = "indeterminate"


class ConfidenceLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RelevanceJudgment(StrEnum):
    RELEVANT = "relevant"
    PARTIALLY_RELEVANT = "partially_relevant"
    IRRELEVANT = "irrelevant"
    INDETERMINATE = "indeterminate"


class FactJudgment(BaseModel):
    model_config = ConfigDict(frozen=True)

    fact_id: str = Field(min_length=1)
    verdict: JudgeVerdict
    confidence: ConfidenceLevel
    answer_spans: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    rationale: str = Field(min_length=1, max_length=1000)


class ClaimJudgment(BaseModel):
    model_config = ConfigDict(frozen=True)

    claim: str = Field(min_length=1, max_length=1000)
    support: ClaimSupport
    confidence: ConfidenceLevel
    answer_span: str = Field(min_length=1, max_length=1000)
    evidence_refs: tuple[str, ...] = ()
    rationale: str = Field(min_length=1, max_length=1000)


class BehaviorJudgment(BaseModel):
    model_config = ConfigDict(frozen=True)

    observed_behavior: ExpectedBehavior
    correct: bool
    confidence: ConfidenceLevel
    rationale: str = Field(min_length=1, max_length=1000)


class TaskJudgment(BaseModel):
    """Atomic model judgments; aggregate task success is deliberately absent."""

    model_config = ConfigDict(frozen=True)

    fact_judgments: tuple[FactJudgment, ...] = ()
    claim_judgments: tuple[ClaimJudgment, ...] = ()
    behavior: BehaviorJudgment
    answer_relevance: RelevanceJudgment
    answer_relevance_rationale: str = Field(min_length=1, max_length=1000)
    indeterminate_reason: str | None = Field(default=None, max_length=1000)


class JudgeCallMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str = "vertex_ai"
    model: str
    thinking_level: str
    request_id: str | None = None
    requested_seed: int | None = Field(default=None, ge=0)
    latency_ms: float = Field(ge=0.0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    thought_tokens: int | None = Field(default=None, ge=0)
    retry_count: int = Field(ge=0)
    response_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    response_status: str = Field(min_length=1)


PayloadT = TypeVar("PayloadT", bound=BaseModel)


class JudgeCall(BaseModel, Generic[PayloadT]):
    model_config = ConfigDict(frozen=True)

    payload: PayloadT
    metadata: JudgeCallMetadata


class SpecificationAdjudicationVerdict(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    INDETERMINATE = "indeterminate"


class SpecificationAdjudication(BaseModel):
    model_config = ConfigDict(frozen=True)

    verdict: SpecificationAdjudicationVerdict
    problem_spec_aligned: bool
    required_facts_supported: bool
    answerability_consistent: bool
    behavior_consistent: bool
    tool_independent: bool
    unsupported_fact_ids: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()
    rationale: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def accepted_verdict_requires_all_checks(self) -> SpecificationAdjudication:
        checks = (
            self.problem_spec_aligned,
            self.required_facts_supported,
            self.answerability_consistent,
            self.behavior_consistent,
            self.tool_independent,
        )
        if self.verdict == SpecificationAdjudicationVerdict.ACCEPT and not all(checks):
            raise ValueError("accepted specification requires every check to pass")
        return self
