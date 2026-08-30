from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


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
    MACHINE_ADJUDICATED = "machine_adjudicated"
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


class TrialStatus(StrEnum):
    COMPLETED = "completed"
    SYSTEM_FAILED = "system_failed"
    TIMED_OUT = "timed_out"
    GRADING_FAILED = "grading_failed"
    HARNESS_FAILED = "harness_failed"


class TrialFailureStage(StrEnum):
    EXECUTION = "execution"
    GRADING = "grading"
    HARNESS = "harness"


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


class SuppliedContext(BaseModel):
    """Context available to the system before it starts solving the problem."""

    model_config = ConfigDict(frozen=True)

    key: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    value: str = Field(min_length=1)


class ProblemProvenance(BaseModel):
    """Where a problem came from; this is not part of its success definition."""

    model_config = ConfigDict(frozen=True)

    source_dataset: str = Field(min_length=1)
    source_record_id: str = Field(min_length=1)
    generation_method: str = Field(min_length=1)
    legacy_split: str | None = None


class ProblemRecord(BaseModel):
    """A user problem, independent of success criteria, tools, and system runs.

    ``query_id`` and ``text`` remain accepted as input aliases so historical code can
    be read during migration. New artifacts always serialize ``problem_id`` and
    ``user_utterance``.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    problem_id: str = Field(
        min_length=1,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
        validation_alias=AliasChoices("problem_id", "query_id"),
    )
    user_utterance: str = Field(
        min_length=1,
        validation_alias=AliasChoices("user_utterance", "text"),
    )
    information_need: str | None = Field(default=None, min_length=1)
    world_id: str = Field(default="unspecified", min_length=1)
    supplied_context: tuple[SuppliedContext, ...] = ()
    language: str = Field(default="ko-KR", min_length=2)
    source: QuerySource
    portfolio: PortfolioRole
    characteristics: QueryCharacteristics
    leakage_group_ids: tuple[str, ...] = ()
    provenance: ProblemProvenance | None = None

    @property
    def query_id(self) -> str:
        """Compatibility accessor for pre-task-centric evaluation code."""

        return self.problem_id

    @property
    def text(self) -> str:
        """Compatibility accessor for pre-task-centric evaluation code."""

        return self.user_utterance

    @model_validator(mode="after")
    def validate_context_and_leakage_groups(self) -> ProblemRecord:
        context_keys = [item.key for item in self.supplied_context]
        if len(context_keys) != len(set(context_keys)):
            raise ValueError("supplied context keys must be unique")
        if len(self.leakage_group_ids) != len(set(self.leakage_group_ids)):
            raise ValueError("leakage_group_ids must be unique")
        return self


# Import compatibility only. Canonical artifacts and APIs use ProblemRecord.
QueryRecord = ProblemRecord


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
        if (
            self.judgment != EvidenceJudgment.KNOWN_RELEVANT
            and self.supports_fact_ids
        ):
            raise ValueError("only known relevant evidence can support required facts")
        return self


class EvalSpecification(BaseModel):
    """Versioned success definition for a ProblemRecord."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    spec_id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    spec_version: str = Field(min_length=1)
    problem_id: str = Field(
        min_length=1,
        validation_alias=AliasChoices("problem_id", "query_id"),
    )
    answerability: Answerability
    required_facts: tuple[RequiredFact, ...] = ()
    expected_behaviors: tuple[ExpectedBehavior, ...] = Field(min_length=1)
    evidence_assessments: tuple[EvidenceAssessment, ...] = ()
    review_status: ReviewStatus
    reviewer_ids: tuple[str, ...] = ()
    grader_rubric_version: str | None = None

    @property
    def query_id(self) -> str:
        """Compatibility accessor for historical query-keyed runners."""

        return self.problem_id

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
        evidence_refs = [item.evidence_ref for item in self.evidence_assessments]
        if len(evidence_refs) != len(set(evidence_refs)):
            raise ValueError("evidence_ref values must be unique within a specification")
        if len(self.reviewer_ids) != len(set(self.reviewer_ids)):
            raise ValueError("reviewer_ids must be unique")
        if self.review_status == ReviewStatus.HUMAN_REVIEWED and not self.reviewer_ids:
            raise ValueError("human-reviewed specifications require reviewer_ids")
        needs_rubric = any(
            fact.grader in {GraderKind.LLM_JUDGE, GraderKind.HUMAN}
            for fact in self.required_facts
        )
        if needs_rubric and not self.grader_rubric_version:
            raise ValueError("LLM/human-graded facts require grader_rubric_version")
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
    known_gold_evidence_injected: bool = False


class OutcomeScores(BaseModel):
    model_config = ConfigDict(frozen=True)

    task_success: bool
    required_fact_coverage: float = Field(ge=0.0, le=1.0)
    groundedness: float | None = Field(default=None, ge=0.0, le=1.0)
    answer_relevance: float | None = Field(default=None, ge=0.0, le=1.0)
    behavior_correct: bool


class RetrievalDiagnostics(BaseModel):
    model_config = ConfigDict(frozen=True)

    cutoff_k: int | None = Field(default=None, ge=1)
    known_relevant_recall_at_k: float | None = Field(default=None, ge=0.0, le=1.0)
    judged_precision_at_k: float | None = Field(default=None, ge=0.0, le=1.0)
    ndcg_at_k: float | None = Field(default=None, ge=0.0, le=1.0)
    unjudged_at_k: int | None = Field(default=None, ge=0)
    answer_bearing_evidence_retrieved: bool | None = None

    @model_validator(mode="after")
    def require_cutoff_for_at_k_metrics(self) -> RetrievalDiagnostics:
        at_k_values = (
            self.known_relevant_recall_at_k,
            self.judged_precision_at_k,
            self.ndcg_at_k,
            self.unjudged_at_k,
        )
        if any(value is not None for value in at_k_values) and self.cutoff_k is None:
            raise ValueError("retrieval @k metrics require cutoff_k")
        if (
            self.unjudged_at_k is not None
            and self.cutoff_k is not None
            and self.unjudged_at_k > self.cutoff_k
        ):
            raise ValueError("unjudged_at_k cannot exceed cutoff_k")
        return self


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
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    retrieval_context_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0.0)
    telemetry_complete: bool = False
    measurement_notes: str | None = None


class GraderEfficiencyObservation(BaseModel):
    """Judge-side telemetry, kept separate from system-under-test efficiency."""

    model_config = ConfigDict(frozen=True)

    latency_ms: float = Field(ge=0.0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    thought_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0.0)
    retry_count: int = Field(default=0, ge=0)
    telemetry_complete: bool = False
    measurement_notes: str | None = None


class TrialRunResult(BaseModel):
    """One stochastic trial. Outcome, diagnostics, and efficiency stay separable."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    run_id: str = Field(min_length=1)
    system_version: str = Field(min_length=1)
    problem_id: str = Field(
        min_length=1,
        validation_alias=AliasChoices("problem_id", "query_id"),
    )
    spec_id: str = Field(min_length=1)
    spec_version: str = Field(min_length=1)
    trial_id: str = Field(min_length=1)
    status: TrialStatus = TrialStatus.COMPLETED
    requested_seed: int | None = Field(default=None, ge=0)
    effective_seed: int | None = Field(default=None, ge=0)
    requested_grader_seed: int | None = Field(default=None, ge=0)
    effective_grader_seed: int | None = Field(default=None, ge=0)
    grader_request_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    provider_request_id: str | None = None
    versions: ArtifactVersions
    condition: ExperimentCondition = Field(
        default_factory=lambda: ExperimentCondition(name="agent_selected")
    )
    retrieved_evidence_refs: tuple[str, ...] = ()
    final_answer: str
    outcome: OutcomeScores
    retrieval: RetrievalDiagnostics = Field(default_factory=RetrievalDiagnostics)
    tool_trace: tuple[ToolCallTrace, ...] = ()
    tool_trace_complete: bool = False
    efficiency: EfficiencyObservation
    grader_efficiency: GraderEfficiencyObservation | None = None
    grade_artifact_ref: str | None = None
    grade_details: dict[str, object] | None = None
    error_type: str | None = None
    error_message: str | None = Field(default=None, max_length=1000)
    failure_stage: TrialFailureStage | None = None

    @property
    def query_id(self) -> str:
        """Compatibility accessor for historical paired-comparison code."""

        return self.problem_id

    @field_validator("started_at", "finished_at")
    @classmethod
    def timestamps_require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("trial timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_tool_sequence(self) -> TrialRunResult:
        sequences = [call.sequence for call in self.tool_trace]
        if sequences != list(range(1, len(sequences) + 1)):
            raise ValueError("tool trace sequence must be contiguous and start at 1")
        if self.started_at and self.finished_at and self.finished_at < self.started_at:
            raise ValueError("finished_at must be on or after started_at")
        if self.status == TrialStatus.COMPLETED:
            if (
                self.error_type is not None
                or self.error_message is not None
                or self.failure_stage is not None
            ):
                raise ValueError("completed trials cannot contain an error")
        else:
            if not self.error_type:
                raise ValueError("non-completed trials require error_type")
            if self.failure_stage is None:
                raise ValueError("non-completed trials require failure_stage")
            if self.outcome.task_success:
                raise ValueError("non-completed trials cannot be task successes")
            if self.status in {TrialStatus.SYSTEM_FAILED, TrialStatus.TIMED_OUT}:
                if self.failure_stage != TrialFailureStage.EXECUTION:
                    raise ValueError("system failures/timeouts require execution stage")
            elif self.status == TrialStatus.GRADING_FAILED:
                if self.failure_stage != TrialFailureStage.GRADING:
                    raise ValueError("grading failures require grading stage")
            elif self.failure_stage != TrialFailureStage.HARNESS:
                raise ValueError("harness failures require harness stage")
        return self
