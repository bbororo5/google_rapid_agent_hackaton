"""LLM-facing output schemas for ADK `output_schema`.

Gemini's response_schema rejects `additionalProperties` (emitted by Pydantic
`extra="forbid"`) and is picky about `pattern`/length constraints. So these are
LOOSE mirrors of the contract models — same shape, no forbid/pattern/min_length.

The contract is still enforced: workers re-validate the returned dict against the
STRICT models in app.contracts (which DO forbid extras + check id patterns).
So Gemini gets a clean schema; the boundary stays strict.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.contracts import Channel, Confidence


class DateRangeOut(BaseModel):
    start: str
    end: str


class SignalOut(BaseModel):
    id: str  # must look like sig_... (enforced on re-validation; see instruction)
    type: str
    title: str
    description: str
    metric_name: str
    current_value: float
    baseline_value: float
    lift_ratio: float
    date_window: DateRangeOut
    confidence: Confidence
    evidence_refs: list[str]


class HypothesisOut(BaseModel):
    id: str  # hyp_...
    signal_ids: list[str]
    statement: str
    rationale: str
    confidence: Confidence
    supporting_evidence_refs: list[str]
    caveats: list[str]


class ExperimentItemOut(BaseModel):
    id: str  # exp_...
    hypothesis_id: str
    title: str
    channel: Channel
    content_format: str
    hook: str
    cta: str
    target_metric: str
    success_criteria: str
    scheduled_at: str
    production_brief: str


class ExperimentPlanOut(BaseModel):
    id: str  # plan_...
    summary: str
    overall_confidence: Confidence
    items: list[ExperimentItemOut]


class SignalDraftOut(BaseModel):
    signals: list[SignalOut]


class HypothesisDraftOut(BaseModel):
    hypotheses: list[HypothesisOut]


class ExperimentPlanDraftOut(BaseModel):
    experiment_plan: ExperimentPlanOut
