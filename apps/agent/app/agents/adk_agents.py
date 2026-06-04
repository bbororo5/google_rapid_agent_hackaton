"""Real ADK/Gemini workers.

Each worker is an LlmAgent with output_schema set to the contract 05 model, so
Gemini's final reply is structured and validated. `google.adk` is imported
lazily so the stub path works without the package installed.

The orchestrator invokes one agent at a time (not SequentialAgent) because it
interleaves deterministic review + WS events + backtracking between workers.
"""
from __future__ import annotations

import json
import uuid

from app.agents import instructions
from app.config import get_settings
from app.contracts import (
    ExperimentPlanDraftOutput,
    HypothesisDraftOutput,
    SignalDraftOutput,
)
from app.tools import evidence

_APP = "launchpilot"


def _build_agents():
    from google.adk.agents import LlmAgent

    model = get_settings().gemini_model
    analyst = LlmAgent(
        name="analyst",
        model=model,
        description="Detects quantitative performance signals.",
        instruction=instructions.ANALYST,
        tools=[evidence.query_metric_baseline, evidence.search_content_posts],
        output_schema=SignalDraftOutput,
        output_key="signals",
    )
    strategist = LlmAgent(
        name="strategist",
        model=model,
        description="Generates causal hypotheses.",
        instruction=instructions.STRATEGIST,
        tools=[evidence.search_team_notes],
        output_schema=HypothesisDraftOutput,
        output_key="hypotheses",
    )
    writer = LlmAgent(
        name="writer",
        model=model,
        description="Drafts next-week experiments.",
        instruction=instructions.WRITER,
        output_schema=ExperimentPlanDraftOutput,
        output_key="experiment_plan",
    )
    return {"analyst": analyst, "strategist": strategist, "writer": writer}


async def run_structured(kind: str, user_text: str) -> dict:
    """Run one worker agent and return its parsed JSON output (a dict)."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    agent = _build_agents()[kind]
    session_service = InMemorySessionService()
    runner = Runner(agent=agent, app_name=_APP, session_service=session_service)
    sid = f"sess_{uuid.uuid4().hex[:8]}"
    await session_service.create_session(app_name=_APP, user_id="orchestrator", session_id=sid)

    content = types.Content(role="user", parts=[types.Part(text=user_text)])
    final_text: str | None = None
    async for event in runner.run_async(
        user_id="orchestrator", session_id=sid, new_message=content
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = event.content.parts[0].text

    if not final_text:
        raise RuntimeError(f"{kind}: empty agent response")
    return json.loads(final_text)
