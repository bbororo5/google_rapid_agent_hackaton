"""Pydantic models mirroring the LaunchPilot contracts (02 + 05).

Source of truth = the JSON Schema / OpenAPI / AsyncAPI files under contracts/.
If those change, change here too. tests/test_contract_conformance.py validates
the shipped contract example JSONs against these models.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    """additionalProperties: false."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------
# Shared enums
# --------------------------------------------------------------------------
class Channel(str, Enum):
    youtube = "youtube"
    tiktok = "tiktok"
    instagram = "instagram"
    x = "x"
    unknown = "unknown"


class Confidence(str, Enum):
    low = "low"
    medium = "medium"
    medium_high = "medium_high"
    high = "high"


class AgentRunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING_SIGNAL_DETECTION = "RUNNING_SIGNAL_DETECTION"
    RUNNING_EVIDENCE_SEARCH = "RUNNING_EVIDENCE_SEARCH"
    RUNNING_HYPOTHESIS_GENERATION = "RUNNING_HYPOTHESIS_GENERATION"
    RUNNING_EXPERIMENT_GENERATION = "RUNNING_EXPERIMENT_GENERATION"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AgentRunStage(str, Enum):
    IMPORT_METRICS = "IMPORT_METRICS"
    DETECT_PERFORMANCE_SIGNAL = "DETECT_PERFORMANCE_SIGNAL"
    GROUND_WITH_EVIDENCE = "GROUND_WITH_EVIDENCE"
    GENERATE_HYPOTHESIS = "GENERATE_HYPOTHESIS"
    DRAFT_EXPERIMENT_PLAN = "DRAFT_EXPERIMENT_PLAN"
    WAIT_FOR_APPROVAL = "WAIT_FOR_APPROVAL"
    APPLY_APPROVED_PLAN = "APPLY_APPROVED_PLAN"


class AgentStepStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class AgentObservationKind(str, Enum):
    progress = "progress"
    evidence = "evidence"
    signal = "signal"
    hypothesis = "hypothesis"
    plan = "plan"
    warning = "warning"


class AgentWorkflowEventType(str, Enum):
    run_started = "run.started"
    step_updated = "step.updated"
    observation_created = "observation.created"
    signal_detected = "signal.detected"
    hypothesis_created = "hypothesis.created"
    experiment_plan_drafted = "experiment_plan.drafted"
    run_cancelled = "run.cancelled"
    run_failed = "run.failed"


class InternalAgentCommandType(str, Enum):
    run_cancel = "run.cancel"


class ToolCallStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class ValidationSeverity(str, Enum):
    none = "none"
    warning = "warning"
    blocking = "blocking"


class ValidationIssueCode(str, Enum):
    SCHEMA_INVALID = "SCHEMA_INVALID"
    UNKNOWN_EVIDENCE_REF = "UNKNOWN_EVIDENCE_REF"
    UNKNOWN_SIGNAL_ID = "UNKNOWN_SIGNAL_ID"
    UNKNOWN_HYPOTHESIS_ID = "UNKNOWN_HYPOTHESIS_ID"
    EMPTY_EXPERIMENT_PLAN = "EMPTY_EXPERIMENT_PLAN"
    MISSING_SUCCESS_CRITERIA = "MISSING_SUCCESS_CRITERIA"
    MISSING_SCHEDULE = "MISSING_SCHEDULE"
    LOW_CONFIDENCE_WITHOUT_CAVEAT = "LOW_CONFIDENCE_WITHOUT_CAVEAT"
    UNSUPPORTED_CHANNEL = "UNSUPPORTED_CHANNEL"
    UNSAFE_OR_UNGROUNDED_CLAIM = "UNSAFE_OR_UNGROUNDED_CLAIM"


class ErrorCode(str, Enum):
    INVALID_REQUEST = "INVALID_REQUEST"
    RUN_NOT_FOUND = "RUN_NOT_FOUND"
    RUN_ID_CONFLICT = "RUN_ID_CONFLICT"
    AGENT_BUSY = "AGENT_BUSY"
    TOOL_CALL_FAILED = "TOOL_CALL_FAILED"
    GEMINI_FAILED = "GEMINI_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    INTERNAL_AGENT_ERROR = "INTERNAL_AGENT_ERROR"


_RUN = r"^run_[A-Za-z0-9_]+$"
_SIG = r"^sig_[A-Za-z0-9_]+$"
_HYP = r"^hyp_[A-Za-z0-9_]+$"
_EXP = r"^exp_[A-Za-z0-9_]+$"
_PLAN = r"^plan_[A-Za-z0-9_]+$"
_BRIEF = r"^brief_[A-Za-z0-9_]+$"
_REQ = r"^req_[A-Za-z0-9_]+$"
_TRC = r"^trc_[A-Za-z0-9_]+$"


# --------------------------------------------------------------------------
# Domain objects (shared by 02 + 05)
# --------------------------------------------------------------------------
class DateRange(_Strict):
    start: str
    end: str


class Signal(_Strict):
    id: str = Field(pattern=_SIG)
    type: str
    title: str
    description: str
    metric_name: str
    current_value: float
    baseline_value: float
    lift_ratio: float
    date_window: DateRange
    confidence: Confidence
    evidence_refs: list[str]


class Hypothesis(_Strict):
    id: str = Field(pattern=_HYP)
    signal_ids: list[str] = Field(min_length=1)
    statement: str
    rationale: str
    confidence: Confidence
    supporting_evidence_refs: list[str]
    caveats: list[str]


class ExperimentItem(_Strict):
    id: str = Field(pattern=_EXP)
    hypothesis_id: str = Field(pattern=_HYP)
    title: str
    channel: Channel
    content_format: str
    hook: str
    cta: str
    target_metric: str
    success_criteria: str
    scheduled_at: str
    production_brief: str


class ExperimentPlan(_Strict):
    id: str = Field(pattern=_PLAN)
    summary: str
    overall_confidence: Confidence
    items: list[ExperimentItem]


class AgentResultPayload(_Strict):
    signals: list[Signal]
    hypotheses: list[Hypothesis]
    experiment_plan: ExperimentPlan


# --------------------------------------------------------------------------
# Worker structured outputs (05) — what each LlmAgent returns
# --------------------------------------------------------------------------
class SignalDraftOutput(_Strict):
    signals: list[Signal] = Field(min_length=1)


class HypothesisDraftOutput(_Strict):
    hypotheses: list[Hypothesis] = Field(min_length=1)


class ExperimentPlanDraftOutput(_Strict):
    experiment_plan: ExperimentPlan


class ValidationIssue(_Strict):
    code: ValidationIssueCode
    message: str
    path: str
    suggested_fix: str


class ValidationReport(_Strict):
    passed: bool
    severity: ValidationSeverity
    issues: list[ValidationIssue]
    retry_instruction: Optional[str] = None


# --------------------------------------------------------------------------
# 02 REST run API
# --------------------------------------------------------------------------
class TraceContext(_Strict):
    request_id: str = Field(pattern=_REQ)
    source: str = Field(pattern=r"^java-backend$")
    otel_trace_id: Optional[str] = None


class InternalAgentRunRequest(_Strict):
    agent_run_id: str = Field(pattern=_RUN)
    workspace_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    question: str = Field(min_length=1, max_length=2000)
    date_range: DateRange
    parent_brief_id: Optional[str] = Field(default=None, pattern=_BRIEF)
    trace_context: TraceContext


class InternalAgentRunAcceptedResponse(_Strict):
    ok: bool = True
    agent_run_id: str = Field(pattern=_RUN)
    status: str = "PENDING"
    stream_url: str
    snapshot_url: str
    accepted_at: str


class ToolCallLog(_Strict):
    sequence: int = Field(ge=1)
    tool_name: str
    status: ToolCallStatus
    duration_ms: Optional[int] = Field(default=None, ge=0)
    error_message: Optional[str] = None


class AgentDiagnostics(_Strict):
    worker: Optional[str] = None
    validator_passed: Optional[bool] = None
    backtrack_count: int = Field(ge=0)
    phoenix_reflection_used: bool
    trace_id: Optional[str] = Field(default=None, pattern=_TRC)


class InternalAgentRunStatusResponse(_Strict):
    agent_run_id: str = Field(pattern=_RUN)
    status: AgentRunStatus
    current_stage: Optional[str] = None
    retry_count: int = Field(ge=0)
    error_message: Optional[str] = None
    payload: Optional[AgentResultPayload] = None
    tool_call_logs: list[ToolCallLog]
    agent_diagnostics: AgentDiagnostics
    started_at: Optional[str] = None
    updated_at: str
    completed_at: Optional[str] = None


class InternalAgentRunCancelledResponse(_Strict):
    ok: bool = True
    agent_run_id: str = Field(pattern=_RUN)
    status: str = "CANCELLED"
    cancelled_at: str


class ErrorBody(_Strict):
    code: ErrorCode
    message: str
    request_id: str
    details: Optional[dict] = None


class ErrorResponse(_Strict):
    ok: bool = False
    error: ErrorBody


# --------------------------------------------------------------------------
# 02 WS workflow stream
# --------------------------------------------------------------------------
class AgentStepSnapshot(_Strict):
    id: str
    order: int = Field(ge=1)
    stage: AgentRunStage
    status: AgentStepStatus


class AgentObservation(_Strict):
    id: str
    kind: AgentObservationKind
    title: str
    summary: str
    evidence_refs: Optional[list[str]] = None


class AgentWorkflowEvent(_Strict):
    event_id: str
    type: AgentWorkflowEventType
    agent_run_id: str = Field(pattern=_RUN)
    sequence: int = Field(ge=1)
    occurred_at: str
    status: Optional[AgentRunStatus] = None
    step: Optional[AgentStepSnapshot] = None
    observation: Optional[AgentObservation] = None
    payload: Optional[AgentResultPayload] = None
    error_message: Optional[str] = None


class InternalAgentCommand(_Strict):
    command_id: str
    type: InternalAgentCommandType
    agent_run_id: str = Field(pattern=_RUN)
    reason: Optional[str] = None
