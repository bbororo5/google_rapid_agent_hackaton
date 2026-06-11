"""Real ADK/Gemini workers.

Each worker is an LlmAgent with output_schema set to the contract 05 model, so
Gemini's final reply is structured and validated. `google.adk` is imported
lazily so module import stays cheap; real worker execution requires ADK.

The orchestrator invokes one phase agent per user-requested round. It does not
use SequentialAgent because the product workflow is HITL and non-linear.
"""
from __future__ import annotations

import asyncio
from functools import cached_property
import json
import logging
import os
import time
import uuid

from app.agents import instructions
from app.agents.output_schemas import (
    ExperimentPlanDraftOut,
    HypothesisDraftOut,
    SignalDraftOut,
    TurnInterpreterOut,
)
from app.config import get_settings
from app.tools import evidence

_APP = "launchpilot"

_log = logging.getLogger("launchpilot.adk")
# Hard ceiling per worker LLM call. Without this a hung Gemini/Vertex connection
# (intermittent ConnectError that the SDK keeps retrying) stalls the whole
# pipeline forever and the turn looks "stuck". On timeout we raise, which the
# orchestrator turns into a visible retryable error block.
_LLM_TIMEOUT_S = float(os.environ.get("LLM_CALL_TIMEOUT_S", "180"))


def _build_agents():
    # Imported here (not at module top) so importing this module never requires
    # google-adk unless we actually run in real-LLM mode.
    from google.adk.agents import LlmAgent
    from google.adk.models import Gemini
    from google.adk.planners import BuiltInPlanner
    from google.genai import Client
    from google.genai import types

    settings = get_settings()
    model_id = settings.gemini_model
    model = model_id
    if settings.use_enterpriseai:
        class EnterpriseGemini(Gemini):
            @cached_property
            def api_client(self) -> Client:
                return Client(
                    enterprise=True,
                    project=settings.google_cloud_project,
                    location=settings.google_cloud_location,
                )

        model = EnterpriseGemini(model=model_id)

    planner = None
    if settings.gemini_thinking_budget is not None:
        planner = BuiltInPlanner(
            thinking_config=types.ThinkingConfig(
                thinking_budget=settings.gemini_thinking_budget,
                include_thoughts=False,
            )
        )
    elif settings.gemini_thinking_level:
        thinking_level = getattr(types.ThinkingLevel, settings.gemini_thinking_level.upper())
        planner = BuiltInPlanner(
            thinking_config=types.ThinkingConfig(
                thinking_level=thinking_level,
                include_thoughts=False,
            )
        )
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
    model = get_settings().gemini_model
    t0 = time.monotonic()
    _log.info("worker %s: gemini call start (model=%s shape=%s timeout=%.0fs)",
              kind, model, shape, _LLM_TIMEOUT_S)
    try:
        result = await asyncio.wait_for(collect(), timeout=_LLM_TIMEOUT_S)
    except asyncio.TimeoutError:
        _log.error("worker %s: gemini call TIMED OUT after %.0fs (model=%s)",
                   kind, _LLM_TIMEOUT_S, model)
        raise RuntimeError(f"{kind}: gemini call timed out after {_LLM_TIMEOUT_S:.0f}s")
    _log.info("worker %s: gemini call done in %dms", kind, int((time.monotonic() - t0) * 1000))
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


async def run_text(kind: str, user_text: str) -> str:
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

    async def _collect() -> str | None:
        final_text: str | None = None
        async for event in runner.run_async(
            user_id="orchestrator", session_id=sid, new_message=content
        ):
            if event.is_final_response() and event.content and event.content.parts:
                final_text = event.content.parts[0].text
        return final_text

    final_text = await _run_with_timeout(kind, "text", _collect)
    if not final_text:
        raise RuntimeError(f"{kind}: empty agent response")
    return final_text
