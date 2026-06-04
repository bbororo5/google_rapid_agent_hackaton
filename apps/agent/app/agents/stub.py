"""Deterministic stub workers (no LLM).

Used when GEMINI_API_KEY is unset so the contract-enforced golden path runs and
is testable offline. They call the same evidence wrapper (contract 04) and emit
the same structured outputs (contract 05) as the real ADK workers, just without
Gemini's reasoning. The orchestration, validation, events, and API are identical
either way.
"""
from __future__ import annotations

from app.config import get_settings
from app.contracts import (
    Channel,
    Confidence,
    DateRange,
    ExperimentItem,
    ExperimentPlan,
    ExperimentPlanDraftOutput,
    Hypothesis,
    HypothesisDraftOutput,
    Signal,
    SignalDraftOutput,
)
from app.ids import experiment_id, hypothesis_id, plan_id, signal_id
from app.tools import evidence

# Demo probe order (agent-tool-spec §6: save_rate first).
_PROBE = [("save_rate", "tiktok"), ("save_rate", "youtube"), ("shares", "tiktok")]


def _confidence(lift: float) -> Confidence:
    s = get_settings()
    if lift >= s.signal_threshold_high:
        return Confidence.high
    if lift >= s.signal_threshold_low:
        return Confidence.medium
    return Confidence.low


def analyst(question: str, date_range: DateRange) -> SignalDraftOutput:
    s = get_settings()
    signals: list[Signal] = []
    for metric, channel in _PROBE:
        base = evidence.query_metric_baseline(metric, channel)
        if not base.get("ok"):
            continue
        lift = base["lift_ratio"]
        if lift < s.signal_threshold_low:
            continue
        refs = list(base["evidence_refs"])
        posts = evidence.search_content_posts([channel], metric)
        if posts.get("ok"):
            refs += posts["evidence_refs"]
        signals.append(
            Signal(
                id=signal_id(),
                type="performance_spike",
                title=f"{metric} on {channel} is {lift}x baseline",
                description=(
                    f"{metric} moved from {base['baseline_value']} to "
                    f"{base['current_value']} ({lift}x) on {channel}."
                ),
                metric_name=metric,
                current_value=base["current_value"],
                baseline_value=base["baseline_value"],
                lift_ratio=lift,
                date_window=date_range,
                confidence=_confidence(lift),
                evidence_refs=refs,
            )
        )
    if not signals:  # never emit empty (contract: min 1) — keep weakest probe
        base = evidence.query_metric_baseline(*_PROBE[0])
        signals.append(
            Signal(
                id=signal_id(),
                type="weak_signal",
                title="No strong signal; weakest probe surfaced",
                description="No metric crossed the threshold this window.",
                metric_name=_PROBE[0][0],
                current_value=base.get("current_value", 0.0),
                baseline_value=base.get("baseline_value", 0.0),
                lift_ratio=base.get("lift_ratio", 0.0),
                date_window=date_range,
                confidence=Confidence.low,
                evidence_refs=list(base.get("evidence_refs", [])),
            )
        )
    return SignalDraftOutput(signals=signals)


def strategist(signals: list[Signal]) -> HypothesisDraftOutput:
    hypotheses: list[Hypothesis] = []
    for sig in signals:
        notes = evidence.search_team_notes(sig.metric_name)
        if notes.get("ok"):
            evidence_refs = list(sig.evidence_refs) + list(notes["evidence_refs"])
            statement = f"The {sig.metric_name} lift is associated with recent team activity."
            caveats = ["Association only; not a controlled test."]
        else:  # no qualitative evidence -> quantitative-only + explicit caveat
            evidence_refs = list(sig.evidence_refs)
            statement = f"The {sig.metric_name} lift is associated with an unidentified driver."
            caveats = [
                "No qualitative team-note evidence found; quantitative association only.",
            ]
        hypotheses.append(
            Hypothesis(
                id=hypothesis_id(),
                signal_ids=[sig.id],
                statement=statement,
                rationale=(
                    f"{sig.metric_name} rose to {sig.lift_ratio}x baseline; "
                    "team context suggests a content-driven cause."
                ),
                confidence=sig.confidence,
                supporting_evidence_refs=evidence_refs,
                caveats=caveats,
            )
        )
    return HypothesisDraftOutput(hypotheses=hypotheses)


def writer(hypotheses: list[Hypothesis], date_range: DateRange) -> ExperimentPlanDraftOutput:
    scheduled = f"{date_range.end}T09:00:00+00:00"
    items: list[ExperimentItem] = []
    for hyp in hypotheses:
        items.append(
            ExperimentItem(
                id=experiment_id(),
                hypothesis_id=hyp.id,
                title="Repeat the high-save format next week",
                channel=Channel.tiktok,
                content_format="30s teaser clip",
                hook="Open on the most-saved moment",
                cta="Save for later",
                target_metric="save_rate",
                success_criteria="save_rate >= 1.5x current week within 7 days",
                scheduled_at=scheduled,
                production_brief=(
                    "Recreate the teaser structure that drove the save spike; "
                    "post Tue/Thu mornings."
                ),
            )
        )
    plan = ExperimentPlan(
        id=plan_id(),
        summary="One repeat experiment per hypothesis, anchored on the save-rate spike.",
        overall_confidence=hypotheses[0].confidence if hypotheses else Confidence.low,
        items=items,
    )
    return ExperimentPlanDraftOutput(experiment_plan=plan)
