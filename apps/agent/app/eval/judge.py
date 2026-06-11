"""LLM-as-a-judge for analysis quality (contract 06 §EVALUATOR).

The deterministic reviewer (app/agents/reviewer.py) is a *structural* gate -- it
checks id integrity and required fields, not whether the analysis is any good.
This judge fills that gap: it reads the final AgentResultPayload and scores three
quality axes 1-5 with rationale. It has NO blocking power (ADR-0006: deterministic
validation is authoritative); it only measures.

Separate agent + separate call from the workers, so the model is not grading its
own in-context generation. Lazy ADK import so importing this module never needs
google-adk (the report path still works in stub mode without a judge).
"""
from __future__ import annotations

import json
import uuid

from pydantic import BaseModel, Field

from app.config import get_settings
from app.contracts import AgentResultPayload

_APP = "launchpilot-judge"


# --- Output schema (loose, like app/agents/output_schemas.py, for Gemini) ---
class AxisScore(BaseModel):
    score: int = Field(ge=1, le=5, description="1=poor, 5=excellent")
    rationale: str = Field(description="One or two sentences citing specifics.")


class QualityScore(BaseModel):
    signal_validity: AxisScore = Field(
        description="Are the signals real, meaningful moves backed by evidence_refs?"
    )
    hypothesis_grounding: AxisScore = Field(
        description="Hypotheses cite evidence, avoid causal overreach, hedge low confidence with caveats."
    )
    plan_actionability: AxisScore = Field(
        description="Experiments have measurable success_criteria, concrete channel/schedule, trace to a hypothesis."
    )
    overall: int = Field(ge=1, le=5, description="Holistic 1-5.")
    summary: str = Field(description="One-line verdict.")


_INSTRUCTION = """You are a strict QA reviewer for a growth-marketing analysis agent.
You receive a JSON payload with `signals`, `hypotheses`, and an `experiment_plan`.
When provided, you also receive TOOL EVIDENCE: the ground-truth values the evidence
tools actually returned during the run (`refs` = every evidence ref that exists;
`metrics` = the real current/baseline/lift values per metric ref). Treat the tool
evidence as the source of truth -- the payload may misquote it.

Score the ANALYSIS QUALITY on three axes, 1 (poor) to 5 (excellent):

1. signal_validity: Are signals real, meaningful changes (lift_ratio), grounded by
   evidence_refs? When tool evidence is present, CROSS-CHECK: a signal citing a ref
   absent from `refs`, or quoting numbers that contradict `metrics`, scores 1-2.
   Penalize noise dressed up as signal, or signals with no evidence.
2. hypothesis_grounding: Do hypotheses cite signals/evidence, AVOID causal overreach
   (prefer "associated with" over "caused"), and hedge low/medium confidence with
   caveats? When tool evidence is present, penalize claims that go beyond what the
   cited evidence supports. Penalize ungrounded or overconfident claims.
3. plan_actionability: Does each experiment have a MEASURABLE success_criteria, a
   concrete channel and scheduled_at, and trace to a real hypothesis_id? Penalize
   vague or unschedulable experiments.

Be specific in each rationale (name ids, numbers). Return the QualityScore schema only."""


async def judge(
    payload: AgentResultPayload, evidence_snapshot: dict | None = None
) -> QualityScore:
    """Score one analysis payload. Requires real-LLM mode (raises otherwise).

    evidence_snapshot: GroundingCapture.snapshot() from the same run -- the
    ground-truth tool results the judge cross-checks the payload against.
    Without it the judge can only score plausibility, not grounding.
    """
    if not get_settings().use_real_llm:
        raise RuntimeError("judge requires real-LLM mode (set GEMINI_API_KEY or Vertex ADC)")

    from google.adk.agents import LlmAgent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    agent = LlmAgent(
        name="quality_judge",
        model=get_settings().gemini_model,
        description="Scores analysis quality on three axes.",
        instruction=_INSTRUCTION,
        output_schema=QualityScore,
    )
    session_service = InMemorySessionService()
    runner = Runner(agent=agent, app_name=_APP, session_service=session_service)
    sid = f"judge_{uuid.uuid4().hex[:8]}"
    await session_service.create_session(app_name=_APP, user_id="evaluator", session_id=sid)

    user_text = "Payload to score (JSON):\n" + json.dumps(
        payload.model_dump(mode="json"), ensure_ascii=False
    )
    if evidence_snapshot and evidence_snapshot.get("refs"):
        user_text += "\n\nTOOL EVIDENCE (ground truth from this run):\n" + json.dumps(
            {"refs": sorted(evidence_snapshot["refs"]),
             "metrics": evidence_snapshot.get("metrics") or {}},
            ensure_ascii=False,
        )
    content = types.Content(role="user", parts=[types.Part(text=user_text)])
    final_text: str | None = None
    async for event in runner.run_async(user_id="evaluator", session_id=sid, new_message=content):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = event.content.parts[0].text

    if not final_text:
        raise RuntimeError("judge: empty response")
    return QualityScore(**json.loads(final_text))
