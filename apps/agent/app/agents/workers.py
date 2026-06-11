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
from app.runtime.state import DeltaIntent, PhaseType, ResponseMode, StateDeltaProposal


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
    "need_campaign": "State: campaign context is missing. Ask for a campaign context before analysis.",
    "ready_to_analyze": "State: campaign context is ready, not analyzed yet. Offer to start the analysis.",
    "analysis_done": "State: analysis and experiment plan complete, awaiting approval. Guide the user to review.",
    "": "State: general conversation.",
}


async def run_turn_interpreter(
    content: str,
    context: str = "",
    current_phase: PhaseType = PhaseType.DATA_ANALYSIS,
) -> StateDeltaProposal:
    """Extract a state transition proposal from free-form user text.

    This intentionally does not trust the UI to send state commands. The LLM path
    can still provide a chat reply through the chat worker, but transition
    authority remains deterministic and local until a dedicated interpreter
    output schema is added to the ADK agents.
    """
    text = content.lower()
    chat_context = context.split(";", 1)[0].strip()
    target = _phase_from_text(content, text)
    wants_backtrack = target is not None and target != current_phase
    if _looks_like_artifact_revision(content, text, current_phase) and not wants_backtrack:
        return StateDeltaProposal(
            intent=DeltaIntent.ARTIFACT_REVISION,
            response_mode=ResponseMode.DELEGATE,
            target_phase=current_phase,
            mutation=_extract_mutation(content, text),
            confidence=0.74,
            rationale="phase-local draft artifact revision",
        )
    restart_words = (
        "다시", "처음", "돌아", "재분석", "바꿔", "변경", "수정", "back", "restart",
        "rerun", "redo", "change", "revise", "from scratch",
    )
    if wants_backtrack or (target is not None and any(w in text or w in content for w in restart_words)):
        return StateDeltaProposal(
            intent=DeltaIntent.BACKTRACK,
            response_mode=ResponseMode.RERUN,
            target_phase=target or PhaseType.DATA_ANALYSIS,
            restart_from_phase=target or PhaseType.DATA_ANALYSIS,
            mutation=_extract_mutation(content, text),
            confidence=0.82,
            requires_confirmation=False,
        )

    if _stub_is_analyze(content):
        return StateDeltaProposal(
            intent=DeltaIntent.START_ANALYSIS,
            response_mode=ResponseMode.RERUN,
            target_phase=PhaseType.DATA_ANALYSIS,
            restart_from_phase=PhaseType.DATA_ANALYSIS,
            mutation=_extract_mutation(content, text),
            confidence=0.9,
        )

    approval_words = ("approve", "approved", "승인", "좋아 진행", "다음 단계", "next phase")
    if any(w in text or w in content for w in approval_words):
        return StateDeltaProposal(
            intent=DeltaIntent.APPROVE,
            response_mode=ResponseMode.DIRECT,
            confidence=0.78,
        )

    return StateDeltaProposal(
        intent=DeltaIntent.CHAT,
        response_mode=ResponseMode.DIRECT,
        confidence=0.75,
        reply=await run_chat(content, chat_context),
    )


_ANALYZE_KEYWORDS = (
    "분석", "신호", "지표", "실험", "찾아", "비교", "성과", "리텐션",
    "analyze", "analysis", "signal", "metric", "experiment", "test", "next week",
)


def _stub_is_analyze(content: str) -> bool:
    text = content.lower()
    return any(k in content or k in text for k in _ANALYZE_KEYWORDS)


def _looks_like_artifact_revision(
    content: str,
    text: str,
    current_phase: PhaseType,
) -> bool:
    if current_phase not in (PhaseType.HYPOTHESIS_GEN, PhaseType.EXPERIMENT_PLAN, PhaseType.EXPERIMENT_EVAL):
        return False
    revision_terms = (
        "짧게", "길게", "제목", "문구", "수정", "바꿔", "변경", "다듬",
        "shorter", "longer", "title", "revise", "edit", "rewrite", "change",
    )
    return any(term in content or term in text for term in revision_terms)


def _phase_from_text(content: str, text: str) -> PhaseType | None:
    phase_terms: tuple[tuple[PhaseType, tuple[str, ...]], ...] = (
        (PhaseType.DATA_ANALYSIS, ("1단계", "데이터", "분석", "analysis", "signal", "metric")),
        (PhaseType.HYPOTHESIS_GEN, ("2단계", "가설", "hypothesis", "why")),
        (PhaseType.EXPERIMENT_PLAN, ("3단계", "실험 계획", "계획", "experiment plan", "plan")),
        (PhaseType.EXPERIMENT_EVAL, ("4단계", "평가", "eval", "evaluation", "review")),
    )
    for phase, terms in phase_terms:
        if any(term in content or term in text for term in terms):
            return phase
    return None


def _extract_mutation(content: str, text: str) -> dict:
    mutation: dict = {}
    metric_terms = {
        "save_rate": ("save_rate", "저장률", "저장율", "save rate"),
        "shares": ("shares", "공유", "share"),
        "views": ("views", "조회", "view"),
        "comments": ("comments", "댓글", "comment"),
        "watch_time": ("watch_time", "시청 시간", "watch time"),
    }
    for metric, terms in metric_terms.items():
        if any(term in content or term in text for term in terms):
            mutation["metric"] = metric
            break
    threshold_markers = ("2배", "2x", "two times")
    if any(marker in text or marker in content for marker in threshold_markers):
        mutation["threshold_lift"] = 2.0
    if "다음주" in content or "next week" in text:
        mutation["time_horizon"] = "next_week"
    return mutation


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
