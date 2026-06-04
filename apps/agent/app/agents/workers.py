"""Worker facade: dispatch to stub or ADK, return validated contract models.

The orchestrator only talks to this module, so the rest of the pipeline is
identical in stub and real modes.
"""
from __future__ import annotations

import json

from app.agents import stub
from app.config import get_settings
from app.contracts import (
    ExperimentPlanDraftOutput,
    Hypothesis,
    HypothesisDraftOutput,
    InternalAgentRunRequest,
    Signal,
    SignalDraftOutput,
)


def _dump(models) -> str:
    return json.dumps([m.model_dump(mode="json") for m in models], ensure_ascii=False)


async def run_analyst(req: InternalAgentRunRequest) -> SignalDraftOutput:
    if get_settings().use_real_llm:
        from app.agents import adk_agents

        prompt = (
            f"Question: {req.question}\n"
            f"Date range: {req.date_range.start}..{req.date_range.end}\n"
            "Detect performance signals and return the signal schema."
        )
        data = await adk_agents.run_structured("analyst", prompt)
        return SignalDraftOutput(**data)
    return stub.analyst(req.question, req.date_range)


async def run_strategist(
    req: InternalAgentRunRequest, signals: list[Signal]
) -> HypothesisDraftOutput:
    if get_settings().use_real_llm:
        from app.agents import adk_agents

        prompt = (
            f"Question: {req.question}\n"
            f"Signals (JSON): {_dump(signals)}\n"
            "Generate hypotheses for these signals and return the hypothesis schema."
        )
        data = await adk_agents.run_structured("strategist", prompt)
        return HypothesisDraftOutput(**data)
    return stub.strategist(signals)


async def run_writer(
    req: InternalAgentRunRequest, hypotheses: list[Hypothesis]
) -> ExperimentPlanDraftOutput:
    if get_settings().use_real_llm:
        from app.agents import adk_agents

        prompt = (
            f"Question: {req.question}\n"
            f"Date range: {req.date_range.start}..{req.date_range.end}\n"
            f"Hypotheses (JSON): {_dump(hypotheses)}\n"
            "Draft next-week experiments and return the experiment plan schema."
        )
        data = await adk_agents.run_structured("writer", prompt)
        return ExperimentPlanDraftOutput(**data)
    return stub.writer(hypotheses, req.date_range)
