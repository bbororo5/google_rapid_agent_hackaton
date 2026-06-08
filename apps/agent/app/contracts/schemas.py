"""Pydantic models mirroring the LaunchPilot contracts (02 + 05).

Source of truth = the JSON Schema / OpenAPI / AsyncAPI files under contracts/.
If those change, change here too. tests/test_contract_conformance.py validates
the shipped contract example JSONs against these models.

Conversation-first model (contract 02 v1.0): Java sends user turns to
`POST /internal/agent/turns`; Python streams user-safe block messages over
`WS /internal/agent/threads/{thread_id}/stream`.
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


class BlockKind(str, Enum):
    text = "text"
    activity = "activity"
    markdown_document = "markdown_document"
    artifact = "artifact"
    approval = "approval"
    result = "result"
    error = "error"


class StreamRole(str, Enum):
    assistant = "assistant"
    system = "system"


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
    AGENT_BUSY = "AGENT_BUSY"
    TOOL_CALL_FAILED = "TOOL_CALL_FAILED"
    GEMINI_FAILED = "GEMINI_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    INTERNAL_AGENT_ERROR = "INTERNAL_AGENT_ERROR"


_SIG = r"^sig_[A-Za-z0-9_]+$"
_HYP = r"^hyp_[A-Za-z0-9_]+$"
_EXP = r"^exp_[A-Za-z0-9_]+$"
_PLAN = r"^plan_[A-Za-z0-9_]+$"
_BRIEF = r"^brief_[A-Za-z0-9_]+$"
_REQ = r"^req_[A-Za-z0-9_]+$"
_MSG = r"^msg_[A-Za-z0-9_]+$"
_THREAD = r"^thread_[A-Za-z0-9_]+$"


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
# 02 REST turn API (Java -> Python)
# --------------------------------------------------------------------------
class TraceContext(_Strict):
    request_id: str = Field(pattern=_REQ)
    source: str = Field(pattern=r"^java-backend$")
    otel_trace_id: Optional[str] = None


class AttachmentRef(_Strict):
    kind: str  # csv_import | growth_brief | document | artifact
    id: str


class InternalAgentTurn(_Strict):
    # Inbound is intentionally lenient: Java currently sends trace_context=null
    # and may send null workspace/campaign on a registry miss. Only thread_id +
    # content are hard requirements so a valid turn is never rejected at 422.
    thread_id: str = Field(pattern=_THREAD)
    workspace_id: Optional[str] = None
    campaign_id: Optional[str] = None
    content: str = Field(min_length=1, max_length=4000)
    attachments: list[AttachmentRef] = Field(default_factory=list)
    client_created_at: Optional[str] = None
    trace_context: Optional[TraceContext] = None


class InternalAgentTurnAccepted(_Strict):
    ok: bool = True
    thread_id: str = Field(pattern=_THREAD)
    accepted_at: str


class ErrorBody(_Strict):
    code: ErrorCode
    message: str
    request_id: str
    details: Optional[dict] = None


class ErrorResponse(_Strict):
    ok: bool = False
    error: ErrorBody


# --------------------------------------------------------------------------
# 02 WS block stream (Python -> Java)
# --------------------------------------------------------------------------
class InternalStreamMessage(_Strict):
    id: str = Field(pattern=_MSG)
    thread_id: str = Field(pattern=_THREAD)
    sequence: int = Field(ge=1)
    role: StreamRole
    created_at: str
    # Blocks are open dicts (kind + kind-specific fields) so the agent can emit
    # the full block vocabulary without a model per variant. Each must carry a
    # valid `kind`; the FE/Java contract (01) defines the per-kind fields.
    blocks: list[dict] = Field(min_length=1)
