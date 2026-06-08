"""Worker facade: dispatch to stub or ADK, return validated contract models.

The orchestrator only talks to this module, so the rest of the pipeline is
identical in stub and real modes. Each function returns the same Pydantic output
type regardless of which backend produced it.

Conversation-first: workers take the user's turn `content` (free text) plus a
synthesized analysis `date_range` instead of the old structured run request.
"""
from __future__ import annotations

import json

from app.agents import stub
from app.config import get_settings
from app.contracts import (
    DateRange,
    ExperimentPlanDraftOutput,
    Hypothesis,
    HypothesisDraftOutput,
    Signal,
    SignalDraftOutput,
)


def _dump(models) -> str:
    # Serialize prior-stage outputs to JSON so they can be handed to the next
    # agent inside its user prompt (real-LLM path only).
    return json.dumps([m.model_dump(mode="json") for m in models], ensure_ascii=False)


async def run_analyst(content: str, date_range: DateRange) -> SignalDraftOutput:
    if get_settings().use_real_llm:
        # Real path: build a prompt and let the ADK analyst agent (with its
        # evidence tools + output_schema) return structured signals.
        from app.agents import adk_agents

        prompt = (
            f"User request: {content}\n"
            f"Date range: {date_range.start}..{date_range.end}\n"
            "Detect performance signals and return the signal schema."
        )
        data = await adk_agents.run_structured("analyst", prompt)
        return SignalDraftOutput(**data)  # re-validate against the contract model
    # Stub path: deterministic analyst over seed data.
    return stub.analyst(content, date_range)


async def run_strategist(content: str, signals: list[Signal]) -> HypothesisDraftOutput:
    if get_settings().use_real_llm:
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
    return stub.strategist(signals)


_CHAT_CONTEXT_HINT = {
    # No fresh CSV, but we CAN analyze the existing baseline. Suggest both options.
    "need_csv": ("State: no fresh CSV uploaded. You can analyze the existing baseline data "
                 "right away if the user asks to analyze; you may also invite them to attach "
                 "a campaign metrics CSV for the latest read. Do not imply a CSV is required."),
    # Same state, but we've already nudged about the CSV - don't repeat that suggestion.
    "need_csv_quiet": ("State: no fresh CSV uploaded; you can analyze the existing baseline on "
                       "request. Do NOT suggest uploading a CSV again - just answer helpfully."),
    "ready_to_analyze": "State: campaign data uploaded, not analyzed yet. Offer to start the analysis.",
    "analysis_done": "State: analysis and experiment plan complete, awaiting approval. Guide the user to review.",
    "": "State: general conversation.",
}


async def run_router(content: str, context: str = "") -> dict:
    """One fast pass: classify intent + draft a chat reply.

    Returns {"intent": "analyze"|"chat", "reply": str}. Real mode = one Gemini
    call; stub mode = keyword classify + canned reply (offline/tests).
    """
    if get_settings().use_real_llm:
        from app.agents import adk_agents

        prompt = f"[Thread state] {_CHAT_CONTEXT_HINT.get(context, '')}\n[User] {content}"
        data = await adk_agents.run_structured("router", prompt)
        intent = "analyze" if data.get("intent") == "analyze" else "chat"
        return {"intent": intent, "reply": data.get("reply", "")}
    # Stub: deterministic keyword classify + canned steering reply.
    intent = "analyze" if _stub_is_analyze(content) else "chat"
    return {"intent": intent, "reply": stub.chat(content, context)}


_ANALYZE_KEYWORDS = (
    "분석", "신호", "지표", "실험", "찾아", "비교", "성과", "리텐션",
    "analyze", "analysis", "signal", "metric", "experiment", "test", "next week",
)


def _stub_is_analyze(content: str) -> bool:
    text = content.lower()
    return any(k in content or k in text for k in _ANALYZE_KEYWORDS)


async def run_chat(content: str, context: str = "") -> str:
    """Free conversation reply. Real Gemini chat agent, or a canned stub reply.

    `context` is a thread-state hint so the reply steers toward the next concrete
    step (upload CSV, run analysis, review plan) instead of a context-free chat.
    """
    if get_settings().use_real_llm:
        from app.agents import adk_agents

        prompt = f"[Thread state] {_CHAT_CONTEXT_HINT.get(context, '')}\n[User] {content}"
        return await adk_agents.run_text("chat", prompt)
    return stub.chat(content, context)


async def run_writer(
    content: str, date_range: DateRange, hypotheses: list[Hypothesis]
) -> ExperimentPlanDraftOutput:
    if get_settings().use_real_llm:
        from app.agents import adk_agents

        prompt = (
            f"User request: {content}\n"
            f"Date range: {date_range.start}..{date_range.end}\n"
            f"Hypotheses (JSON): {_dump(hypotheses)}\n"
            "Draft next-week experiments and return the experiment plan schema."
        )
        data = await adk_agents.run_structured("writer", prompt)
        return ExperimentPlanDraftOutput(**data)
    return stub.writer(hypotheses, date_range)
