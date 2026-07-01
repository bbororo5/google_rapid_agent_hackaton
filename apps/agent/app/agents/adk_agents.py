"""Real ADK/Gemini workers.

Each worker is an LlmAgent with output_schema set to the contract 05 model, so
Gemini's final reply is structured and validated. `google.adk` is imported
lazily so module import stays cheap; real worker execution requires ADK.

The orchestrator invokes one phase agent per user-requested round. It does not
use SequentialAgent because the product workflow is HITL and non-linear.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable

from app.agents import instructions
from app.agents.output_schemas import (
    ExperimentPlanDraftOut,
    HypothesisDraftOut,
    SignalDraftOut,
    TurnInterpreterOut,
)
from app.agents.model_factory import build_model, build_planner
from app.config import get_settings
from app.tools import evidence

_APP = "launchpilot"

_log = logging.getLogger("launchpilot.adk")
# Hard ceiling per worker LLM call. Without this a hung Gemini/Vertex connection
# (intermittent ConnectError that the SDK keeps retrying) stalls the whole
# pipeline forever and the turn looks "stuck". On timeout we raise, which the
# orchestrator turns into a visible retryable error block.
_LLM_TIMEOUT_S = float(os.environ.get("LLM_CALL_TIMEOUT_S", "180"))
_TEXT_STREAM_FALLBACK_DELAY_S = float(os.environ.get("TEXT_STREAM_FALLBACK_DELAY_S", "0.035"))
_TEXT_STREAM_FALLBACK_CHARS = int(os.environ.get("TEXT_STREAM_FALLBACK_CHARS", "90"))


def _build_agents():
    # Imported here (not at module top) so importing this module never requires
    # google-adk unless we actually run in real-LLM mode.
    from google.adk.agents import LlmAgent

    settings = get_settings()
    model = build_model(settings)
    planner = build_planner(settings)
    # Analyst: has the two evidence tools AND an output schema. In ADK 2.x tools
    # and output_schema compose (tools run during reasoning, schema shapes the
    # final reply). output_key writes the result into shared session state.
    analyst = LlmAgent(
        name="analyst",
        model=model,
        description="Detects quantitative performance signals.",
        instruction=instructions.ANALYST,
        tools=[evidence.query_metric_baseline, evidence.search_content_posts],
        planner=planner,
        output_schema=SignalDraftOut,
        output_key="signals",
    )
    # Strategist: one tool (team notes) + hypothesis schema.
    strategist = LlmAgent(
        name="strategist",
        model=model,
        description="Generates causal hypotheses.",
        instruction=instructions.STRATEGIST,
        tools=[evidence.search_team_notes],
        planner=planner,
        output_schema=HypothesisDraftOut,
        output_key="hypotheses",
    )
    # Writer: no tools (pure generation) + experiment-plan schema.
    writer = LlmAgent(
        name="writer",
        model=model,
        description="Drafts next-week experiments.",
        instruction=instructions.WRITER,
        planner=planner,
        output_schema=ExperimentPlanDraftOut,
        output_key="experiment_plan",
    )
    # Chat: free conversation. No tools, no output_schema -> plain text reply.
    chat = LlmAgent(
        name="chat",
        model=model,
        description="Conversational replies about campaign growth work.",
        instruction=instructions.CHAT,
        planner=planner,
    )
    advisor = LlmAgent(
        name="advisor",
        model=model,
        description="Context-rich user-facing reasoning and follow-up.",
        instruction=instructions.ADVISOR,
        planner=planner,
    )
    interpreter = LlmAgent(
        name="interpreter",
        model=model,
        description="Interprets free-form turns into state delta proposals.",
        instruction=instructions.INTERPRETER,
        planner=planner,
        output_schema=TurnInterpreterOut,
        output_key="state_delta",
    )
    return {
        "analyst": analyst,
        "strategist": strategist,
        "writer": writer,
        "chat": chat,
        "advisor": advisor,
        "interpreter": interpreter,
    }


async def _run_with_timeout(kind: str, shape: str, collect):
    """Await `collect()` under a hard timeout, logging start/elapsed/timeout.

    Makes each worker's Gemini call visible in the logs and prevents a hung
    connection from stalling the pipeline indefinitely.
    """
    settings = get_settings()
    model = settings.local_llm_model if settings.llm_provider in ("ollama", "local") else settings.gemini_model
    t0 = time.monotonic()
    _log.info("worker %s: llm call start (provider=%s model=%s shape=%s timeout=%.0fs)",
              kind, settings.llm_label, model, shape, _LLM_TIMEOUT_S)
    try:
        result = await asyncio.wait_for(collect(), timeout=_LLM_TIMEOUT_S)
    except asyncio.TimeoutError:
        _log.error("worker %s: llm call TIMED OUT after %.0fs (provider=%s model=%s)",
                   kind, _LLM_TIMEOUT_S, settings.llm_label, model)
        raise RuntimeError(f"{kind}: llm call timed out after {_LLM_TIMEOUT_S:.0f}s")
    _log.info("worker %s: llm call done in %dms", kind, int((time.monotonic() - t0) * 1000))
    return result


async def run_structured(kind: str, user_text: str) -> dict:
    """Run one worker agent and return its parsed JSON output (a dict)."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    agent = _build_agents()[kind]
    # Fresh in-memory session per worker call (the orchestrator threads state
    # itself via prompts, so workers don't need a shared ADK session here).
    session_service = InMemorySessionService()
    runner = Runner(agent=agent, app_name=_APP, session_service=session_service)
    sid = f"sess_{uuid.uuid4().hex[:8]}"
    await session_service.create_session(app_name=_APP, user_id="orchestrator", session_id=sid)

    content = types.Content(role="user", parts=[types.Part(text=user_text)])

    async def _collect() -> str | None:
        final_text: str | None = None
        # run_async yields a stream of events; the structured JSON is on the final one.
        async for event in runner.run_async(
            user_id="orchestrator", session_id=sid, new_message=content
        ):
            if event.is_final_response() and event.content and event.content.parts:
                final_text = event.content.parts[0].text
        return final_text

    final_text = await _run_with_timeout(kind, "structured", _collect)
    if not final_text:
        raise RuntimeError(f"{kind}: empty agent response")
    # output_schema guarantees the final text is schema-conforming JSON.
    return json.loads(final_text)


async def run_text(
    kind: str,
    user_text: str,
    on_delta: Callable[[str], Awaitable[None]] | None = None,
) -> str:
    """Run one agent and return its plain-text reply (no output_schema)."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    agent = _build_agents()[kind]
    session_service = InMemorySessionService()
    runner = Runner(agent=agent, app_name=_APP, session_service=session_service)
    sid = f"sess_{uuid.uuid4().hex[:8]}"
    await session_service.create_session(app_name=_APP, user_id="orchestrator", session_id=sid)

    content = types.Content(role="user", parts=[types.Part(text=user_text)])

    async def _emit_synthetic_stream(text: str) -> None:
        if not on_delta:
            return
        for chunk in _text_stream_chunks(text, _TEXT_STREAM_FALLBACK_CHARS):
            await on_delta(chunk)
            await asyncio.sleep(_TEXT_STREAM_FALLBACK_DELAY_S)

    async def _collect() -> str | None:
        final_text: str | None = None
        streamed_text = ""
        pending_delta = ""

        async def _flush_delta(force: bool = False) -> None:
            nonlocal pending_delta
            if not on_delta or not pending_delta:
                return
            if not force and len(pending_delta) < 80 and "\n" not in pending_delta:
                return
            delta = pending_delta
            pending_delta = ""
            await on_delta(delta)

        async for event in runner.run_async(
            user_id="orchestrator", session_id=sid, new_message=content
        ):
            if not event.content or not event.content.parts:
                continue
            event_text = event.content.parts[0].text or ""
            if event.is_final_response():
                final_text = event_text
                if on_delta and streamed_text and event_text.startswith(streamed_text):
                    tail = event_text[len(streamed_text):]
                    if tail:
                        pending_delta += tail
                        streamed_text = event_text
                continue
            if not on_delta or not event_text:
                continue
            if event_text.startswith(streamed_text):
                delta = event_text[len(streamed_text):]
                streamed_text = event_text
            else:
                delta = event_text
                streamed_text += event_text
            if delta:
                pending_delta += delta
                await _flush_delta()
        await _flush_delta(force=True)
        if on_delta and final_text and not streamed_text:
            await _emit_synthetic_stream(final_text)
        return final_text

    final_text = await _run_with_timeout(kind, "text", _collect)
    if not final_text:
        raise RuntimeError(f"{kind}: empty agent response")
    return final_text


def _text_stream_chunks(text: str, target_chars: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(length, start + target_chars)
        if end < length:
            candidates = [
                text.rfind("\n\n", start, end),
                text.rfind(". ", start, end),
                text.rfind("? ", start, end),
                text.rfind("! ", start, end),
                text.rfind(" ", start, end),
            ]
            split_at = max(candidates)
            if split_at > start + max(24, target_chars // 3):
                end = split_at + (2 if text.startswith("\n\n", split_at) else 1)
        chunks.append(text[start:end])
        start = end
    return chunks
