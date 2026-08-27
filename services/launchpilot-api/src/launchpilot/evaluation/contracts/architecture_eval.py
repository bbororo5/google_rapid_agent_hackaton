from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PortfolioRole(StrEnum):
    FROZEN = "frozen"
    HOLDOUT = "holdout"
    REGRESSION = "regression"
    FRONTIER = "frontier"
    PRODUCTION_SAMPLE = "production_sample"


class QuerySource(StrEnum):
    PRODUCTION = "production"
    EXPERT_AUTHORED = "expert_authored"
    SYNTHETIC = "synthetic"
    REGRESSION = "regression"


class InformationModality(StrEnum):
    STRUCTURED = "structured"
    UNSTRUCTURED = "unstructured"
    MIXED = "mixed"
    RELATIONAL = "relational"


class LexicalNeed(StrEnum):
    NONE = "none"
    EXACT = "exact"
    PARAPHRASE_GAP = "paraphrase_gap"


class TaskShape(StrEnum):
    LOOKUP = "lookup"
    AGGREGATION = "aggregation"
    COMPARISON = "comparison"
    SYNTHESIS = "synthesis"


class SourceCardinality(StrEnum):
    SINGLE = "single_source"
    MULTIPLE = "multi_source"
    UNKNOWN = "unknown"


class Answerability(StrEnum):
    ANSWERABLE = "answerable"
    AMBIGUOUS = "ambiguous"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ExpectedBehavior(StrEnum):
    ANSWER = "answer"
    ABSTAIN = "abstain"
    CLARIFY = "clarify"
    WARN = "warn"


class EvidenceJudgment(StrEnum):
    KNOWN_RELEVANT = "known_relevant"
    KNOWN_IRRELEVANT = "known_irrelevant"
    UNJUDGED = "unjudged"


class ReviewStatus(StrEnum):
    AUTO_VALIDATED = "auto_validated"
    HUMAN_REVIEWED = "human_reviewed"
    NEEDS_REVIEW = "needs_review"


class GraderKind(StrEnum):
    DETERMINISTIC = "deterministic"
    IR_METRIC = "ir_metric"
    LLM_JUDGE = "llm_judge"
    HUMAN = "human"


class ToolCallStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class QueryCharacteristics(BaseModel):
    """Explanatory slices only; these values must never prescribe a tool or route."""

    model_config = ConfigDict(frozen=True)

    modalities: tuple[InformationModality, ...] = Field(min_length=1)
    lexical_need: LexicalNeed = LexicalNeed.NONE
    entity_centric: bool = False
    hop_count: int = Field(default=1, ge=0)
    task_shape: TaskShape
    source_cardinality: SourceCardinality = SourceCardinality.UNKNOWN
    tags: tuple[str, ...] = ()


class QueryRecord(BaseModel):
    """The user problem, independent of any success definition or system run."""

    model_config = ConfigDict(frozen=True)

    query_id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    text: str = Field(min_length=1)
    language: str = Field(default="ko-KR", min_length=2)
    source: QuerySource
    portfolio: PortfolioRole
    characteristics: QueryCharacteristics
    leakage_group_ids: tuple[str, ...] = ()


class RequiredFact(BaseModel):
    model_config = ConfigDict(frozen=True)

    fact_id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    description: str = Field(min_length=1)
    grader: GraderKind
    expected_values: tuple[str, ...] = ()
    unit: str | None = None

    @model_validator(mode="after")
    def deterministic_facts_require_values(self) -> RequiredFact:
        if self.grader == GraderKind.DETERMINISTIC and not self.expected_values:
            raise ValueError("deterministic required facts need expected_values")
        return self


class EvidenceAssessment(BaseModel):
    """One explicit qrel; absence from this list means unjudged, never irrelevant."""

    model_config = ConfigDict(frozen=True)

    evidence_ref: str = Field(min_length=1)
    judgment: EvidenceJudgment
    relevance_grade: int | None = Field(default=None, ge=0, le=3)
    supports_fact_ids: tuple[str, ...] = ()
    assessor_ids: tuple[str, ...] = ()
    rationale: str | None = None

    @model_validator(mode="after")
    def validate_judgment_grade(self) -> EvidenceAssessment:
        if self.judgment == EvidenceJudgment.KNOWN_RELEVANT:
            if self.relevance_grade is None or self.relevance_grade < 1:
                raise ValueError("known relevant evidence requires grade 1..3")
        elif self.judgment == EvidenceJudgment.KNOWN_IRRELEVANT:
            if self.relevance_grade not in (None, 0):
                raise ValueError("known irrelevant evidence can only have grade 0")
        elif self.relevance_grade is not None:
            raise ValueError("unjudged evidence must not have a relevance grade")
        return self


class EvalSpecification(BaseModel):
    """Versioned success definition for a QueryRecord."""

    model_config = ConfigDict(frozen=True)

    spec_id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    spec_version: str = Field(min_length=1)
    query_id: str = Field(min_length=1)
    answerability: Answerability
    required_facts: tuple[RequiredFact, ...] = ()
    expected_behaviors: tuple[ExpectedBehavior, ...] = Field(min_length=1)
    evidence_assessments: tuple[EvidenceAssessment, ...] = ()
    review_status: ReviewStatus
    reviewer_ids: tuple[str, ...] = ()
    grader_rubric_version: str | None = None

    @model_validator(mode="after")
    def validate_behavior_and_fact_refs(self) -> EvalSpecification:
        behaviors = set(self.expected_behaviors)
        if self.answerability == Answerability.ANSWERABLE:
            if ExpectedBehavior.ANSWER not in behaviors:
                raise ValueError("answerable specifications require answer behavior")
        elif not behaviors.intersection(
            {ExpectedBehavior.ABSTAIN, ExpectedBehavior.CLARIFY, ExpectedBehavior.WARN}
        ):
            raise ValueError(
                "non-answerable specifications require abstain, clarify, or warn"
            )

        fact_ids = [fact.fact_id for fact in self.required_facts]
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("required fact ids must be unique within a specification")
        unknown_fact_ids = {
            fact_id
            for evidence in self.evidence_assessments
            for fact_id in evidence.supports_fact_ids
            if fact_id not in fact_ids
        }
        if unknown_fact_ids:
            raise ValueError(
                f"evidence references unknown required facts: {sorted(unknown_fact_ids)}"
            )
        return self


class ArtifactVersions(BaseModel):
    model_config = ConfigDict(frozen=True)

    corpus: str = Field(min_length=1)
    index: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    toolset: str = Field(min_length=1)
    code_commit: str = Field(min_length=1)


class ExperimentCondition(BaseModel):
    """An intervention belongs to the run, not to the query ontology."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    forced_tools: tuple[str, ...] = ()
    oracle_evidence_injected: bool = False


class OutcomeScores(BaseModel):
    model_config = ConfigDict(frozen=True)

    task_success: bool
    required_fact_coverage: float = Field(ge=0.0, le=1.0)
    groundedness: float | None = Field(default=None, ge=0.0, le=1.0)
    answer_relevance: float | None = Field(default=None, ge=0.0, le=1.0)
    behavior_correct: bool


class RetrievalDiagnostics(BaseModel):
    model_config = ConfigDict(frozen=True)

    known_relevant_recall_at_k: float | None = Field(default=None, ge=0.0, le=1.0)
    judged_precision_at_k: float | None = Field(default=None, ge=0.0, le=1.0)
    ndcg_at_k: float | None = Field(default=None, ge=0.0, le=1.0)
    unjudged_at_k: int = Field(default=0, ge=0)
    answer_bearing_evidence_retrieved: bool | None = None


class ToolCallTrace(BaseModel):
    model_config = ConfigDict(frozen=True)

    sequence: int = Field(ge=1)
    tool_name: str = Field(min_length=1)
    status: ToolCallStatus
    latency_ms: float = Field(ge=0.0)
    input_size: int | None = Field(default=None, ge=0)
    output_size: int | None = Field(default=None, ge=0)
    error_type: str | None = None
    recovered: bool = False


class EfficiencyObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    end_to_end_latency_ms: float = Field(ge=0.0)
    retrieval_latency_ms: float | None = Field(default=None, ge=0.0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    retrieval_context_tokens: int = Field(default=0, ge=0)
    cost_usd: float | None = Field(default=None, ge=0.0)


class TrialRunResult(BaseModel):
    """One stochastic trial. Outcome, diagnostics, and efficiency stay separable."""

    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    system_version: str = Field(min_length=1)
    query_id: str = Field(min_length=1)
    spec_id: str = Field(min_length=1)
    spec_version: str = Field(min_length=1)
    trial_id: str = Field(min_length=1)
    versions: ArtifactVersions
    condition: ExperimentCondition = Field(
        default_factory=lambda: ExperimentCondition(name="agent_selected")
    )
    retrieved_evidence_refs: tuple[str, ...] = ()
    final_answer: str
    outcome: OutcomeScores
    retrieval: RetrievalDiagnostics = Field(default_factory=RetrievalDiagnostics)
    tool_trace: tuple[ToolCallTrace, ...] = ()
    efficiency: EfficiencyObservation

    @model_validator(mode="after")
    def validate_tool_sequence(self) -> TrialRunResult:
        sequences = [call.sequence for call in self.tool_trace]
        if sequences != list(range(1, len(sequences) + 1)):
            raise ValueError("tool trace sequence must be contiguous and start at 1")
        return self
