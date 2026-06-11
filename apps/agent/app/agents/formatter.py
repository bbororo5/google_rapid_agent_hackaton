"""Formatter — Python deterministic normalization (decision: not an LLM).

Assembles the three worker outputs into the final AgentResultPayload. Its job is
*structural* only (contract 05). Semantic errors (hallucinated refs, missing
caveat) are NOT fixed here — those route back to a worker via failure.py.

Decision rationale: a SCHEMA_INVALID is a shape slip, not a reasoning error, so
deterministic assembly is correct and cheaper than another LLM hop. With
output_schema enforced upstream this rarely triggers at all.
"""
from __future__ import annotations

from pydantic import ValidationError

from app.contracts import (
    AgentResultPayload,
    ExperimentPlan,
    Hypothesis,
    Signal,
)


class FormatterError(Exception):
    """Structural assembly failed and could not be normalized (SCHEMA_INVALID)."""


def assemble(
    signals: list[Signal],
    hypotheses: list[Hypothesis],
    experiment_plan: ExperimentPlan,
) -> AgentResultPayload:
    try:
        return AgentResultPayload(
            signals=signals,
            hypotheses=hypotheses,
            experiment_plan=experiment_plan,
        )
    except ValidationError as exc:  # shape slip the workers could not satisfy
        raise FormatterError(str(exc)) from exc
