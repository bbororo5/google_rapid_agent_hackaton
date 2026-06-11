"""Worker facade: dispatch to ADK/Gemini, return validated contract models.

The orchestrator only talks to this module, so the rest of the pipeline is
isolated from ADK details. Each function returns a strict Pydantic contract
model.

Conversation-first: workers take the user's turn `content` (free text) plus a
synthesized analysis `date_range` instead of the old structured run request.
"""
from __future__ import annotations

import json

from app.contracts import (
    DateRange,
    ExperimentPlanDraftOutput,
    Hypothesis,
    HypothesisDraftOutput,
    Signal,
    SignalDraftOutput,
)
from app.runtime.state import DeltaIntent, PhaseType, StateDeltaProposal


def _dump(models) -> str:
    # Serialize prior-stage outputs to JSON so they can be handed to the next
    # agent inside its user prompt (real-LLM path only).
    return json.dumps([m.model_dump(mode="json") for m in models], ensure_ascii=False)


async def run_analyst(content: str, date_range: DateRange) -> SignalDraftOutput:
    from app.agents import adk_agents

    prompt = (
        f"User request: {content}\n"
        f"Date range: {date_range.start}..{date_range.end}\n"
        "Detect performance signals and return the signal schema."
    )
    data = await adk_agents.run_structured("analyst", prompt)
    return SignalDraftOutput(**data)  # re-validate against the contract model


async def run_strategist(content: str, signals: list[Signal]) -> HypothesisDraftOutput:
    from app.agents import adk_agents

    # Pass the upstream signals in the prompt so the strategist can ground on
    # them (and reference their ids).
    prompt = (
        f"User request: {content}\n"
        f"Signals (JSON): {_dump(signals)}\n"
        "Generate hypotheses for these signals and return the hypothesis schema."
    )
    data = await adk_agents.run_structured("strategist", prompt)
    return HypothesisDraftOutput(**data)


_CHAT_CONTEXT_HINT = {
    "need_campaign": "State: campaign context is missing. Ask for a campaign context before analysis.",
    "ready_to_analyze": "State: campaign context is ready, not analyzed yet. Offer to start the analysis.",
    "analysis_done": "State: analysis signals exist. Help discuss the signals or move to hypotheses if asked.",
    "plan_ready": "State: an experiment plan exists. Answer questions about the generated or approved plan.",
    "": "State: general conversation.",
}


async def run_turn_interpreter(
    content: str,
    context: str = "",
    current_phase: PhaseType = PhaseType.DATA_ANALYSIS,
) -> StateDeltaProposal:
    """Extract a state transition proposal from free-form user text.

    This intentionally does not trust the UI to send state commands. In real LLM
    mode, a dedicated structured interpreter proposes the delta; the reducer
    remains the authority that accepts or rejects state changes.
    """
    from app.agents import adk_agents

    prompt = (
        f"[Thread state]\n{context}\n"
        f"[Current phase]\n{current_phase.value}\n"
        f"[User]\n{content}"
    )
    data = await adk_agents.run_structured("interpreter", prompt)
    data = {key: (None if value == "" else value) for key, value in data.items()}
    mutation_summary = data.pop("mutation_summary", None)
    if mutation_summary:
        data["mutation"] = {"summary": mutation_summary}
    proposal = StateDeltaProposal(**data)
    if proposal.intent == DeltaIntent.CHAT and not proposal.reply:
        proposal.reply = await run_chat(content, context.split(";", 1)[0].strip())
    return proposal


async def run_chat(content: str, context: str = "") -> str:
    """Free conversation reply from the Gemini chat agent.

    `context` is a thread-state hint so the reply steers toward the next concrete
    step (upload CSV, run analysis, review plan) instead of a context-free chat.
    """
    from app.agents import adk_agents

    prompt = f"[Thread state] {_CHAT_CONTEXT_HINT.get(context, '')}\n[User] {content}"
    return await adk_agents.run_text("chat", prompt)


async def run_writer(
    content: str, date_range: DateRange, hypotheses: list[Hypothesis]
) -> ExperimentPlanDraftOutput:
    from app.agents import adk_agents

    prompt = (
        f"User request: {content}\n"
        f"Date range: {date_range.start}..{date_range.end}\n"
        f"Hypotheses (JSON): {_dump(hypotheses)}\n"
        "Draft next-week experiments and return the experiment plan schema."
    )
    data = await adk_agents.run_structured("writer", prompt)
    return ExperimentPlanDraftOutput(**data)
