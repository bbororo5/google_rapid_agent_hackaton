"""Reviewer gate — deterministic set-based validation (no LLM).

Checks the assembled payload against the contract issue codes (05). Mechanical
cross-id integrity + required fields, plus the grounding gate: when the caller
passes the GroundingCapture snapshot (what the evidence tools actually returned
this run), every cited evidence ref must exist in it and every signal's numbers
must match the tool-returned values. This is the only check that catches an LLM
transcribing/inventing numbers; without a capture (unit tests, legacy callers)
the structural checks still run unchanged.

A failing report routes back to a worker via failure.py; it cannot be overturned
by any LLM critique.
"""
from __future__ import annotations

from app.contracts import (
    AgentResultPayload,
    Channel,
    Confidence,
    ValidationIssue,
    ValidationIssueCode,
    ValidationReport,
    ValidationSeverity,
)

# Confidence levels that REQUIRE at least one caveat to be present.
_LOW_CONFIDENCE = {Confidence.low, Confidence.medium}

# Numeric grounding tolerance: 2% relative. Passes benign rounding the LLM does
# when copying tool values (1.966 -> 1.97) while failing fabricated numbers.
_REL_TOL = 0.02


def _close(a, b) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= max(_REL_TOL * max(abs(a), abs(b)), 1e-9)


def _grounding_issues(payload: AgentResultPayload, grounding: dict) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    known_refs: set = grounding.get("refs") or set()
    metrics: dict = grounding.get("metrics") or {}
    if not known_refs:
        # Tools returned nothing this run (or capture inactive in this context):
        # nothing to ground against, so skip rather than flag everything.
        return issues

    for s in payload.signals:
        # A ref the tools never returned is fabricated -> analyst must re-run.
        unknown = [r for r in s.evidence_refs if r not in known_refs]
        if unknown:
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.UNGROUNDED_EVIDENCE,
                    message=f"signal {s.id} cites evidence refs not returned by any tool: {unknown}",
                    path=f"signals[{s.id}].evidence_refs",
                    suggested_fix="Only cite evidence_refs returned by the evidence tools in this run.",
                )
            )
        # Numeric grounding: the signal's numbers must match a cited metric ref's
        # tool-returned values. Only checked when the signal cites a ref we have
        # numbers for (post/note refs carry no numbers to compare).
        cited_metrics = [metrics[r] for r in s.evidence_refs if r in metrics]
        if cited_metrics and not any(
            m["metric_name"] == s.metric_name
            and _close(m["current_value"], s.current_value)
            and _close(m["baseline_value"], s.baseline_value)
            and _close(m["lift_ratio"], s.lift_ratio)
            for m in cited_metrics
        ):
            got = cited_metrics[0]
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.UNGROUNDED_EVIDENCE,
                    message=(
                        f"signal {s.id} values (metric={s.metric_name} current={s.current_value} "
                        f"baseline={s.baseline_value} lift={s.lift_ratio}) do not match the cited "
                        f"evidence (metric={got['metric_name']} current={got['current_value']} "
                        f"baseline={got['baseline_value']} lift={got['lift_ratio']})"
                    ),
                    path=f"signals[{s.id}]",
                    suggested_fix="Copy current_value/baseline_value/lift_ratio exactly from the tool result.",
                )
            )

    for h in payload.hypotheses:
        unknown = [r for r in h.supporting_evidence_refs if r not in known_refs]
        if unknown:
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.UNKNOWN_EVIDENCE_REF,
                    message=f"hypothesis {h.id} cites evidence refs not returned by any tool: {unknown}",
                    path=f"hypotheses[{h.id}].supporting_evidence_refs",
                    suggested_fix="Only cite evidence_refs returned by the evidence tools in this run.",
                )
            )
    return issues


def review(payload: AgentResultPayload, grounding: dict | None = None) -> ValidationReport:
    issues: list[ValidationIssue] = []
    # Build the id sets we cross-check references against.
    signal_ids = {s.id for s in payload.signals}
    hypothesis_ids = {h.id for h in payload.hypotheses}

    # --- Grounding gate (only when the run captured tool results) ---
    if grounding is not None:
        issues.extend(_grounding_issues(payload, grounding))

    # --- Hypothesis checks ---
    for h in payload.hypotheses:
        # Every signal_id a hypothesis cites must exist (no dangling reference).
        for sid in h.signal_ids:
            if sid not in signal_ids:
                issues.append(
                    ValidationIssue(
                        code=ValidationIssueCode.UNKNOWN_SIGNAL_ID,
                        message=f"hypothesis {h.id} references unknown signal {sid}",
                        path=f"hypotheses[{h.id}].signal_ids",
                        suggested_fix="Reference a signal id produced by the analyst.",
                    )
                )
        # Low/medium confidence claims must be hedged with a caveat.
        if h.confidence in _LOW_CONFIDENCE and not h.caveats:
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.LOW_CONFIDENCE_WITHOUT_CAVEAT,
                    message=f"hypothesis {h.id} is low-confidence but has no caveat",
                    path=f"hypotheses[{h.id}].caveats",
                    suggested_fix="Add at least one caveat for low/medium confidence.",
                )
            )

    # --- Experiment plan checks ---
    plan = payload.experiment_plan
    if not plan.items:
        issues.append(
            ValidationIssue(
                code=ValidationIssueCode.EMPTY_EXPERIMENT_PLAN,
                message="experiment plan has no items",
                path="experiment_plan.items",
                suggested_fix="Add at least one experiment item.",
            )
        )
    for item in plan.items:
        # Each experiment must trace back to a real hypothesis.
        if item.hypothesis_id not in hypothesis_ids:
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.UNKNOWN_HYPOTHESIS_ID,
                    message=f"experiment {item.id} references unknown hypothesis {item.hypothesis_id}",
                    path=f"experiment_plan.items[{item.id}].hypothesis_id",
                    suggested_fix="Reference a hypothesis id produced by the strategist.",
                )
            )
        # Required operational fields must be non-empty.
        if not item.success_criteria.strip():
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.MISSING_SUCCESS_CRITERIA,
                    message=f"experiment {item.id} missing success_criteria",
                    path=f"experiment_plan.items[{item.id}].success_criteria",
                    suggested_fix="Add measurable success criteria.",
                )
            )
        if not item.scheduled_at.strip():
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.MISSING_SCHEDULE,
                    message=f"experiment {item.id} missing scheduled_at",
                    path=f"experiment_plan.items[{item.id}].scheduled_at",
                    suggested_fix="Add a scheduled datetime.",
                )
            )
        # "unknown" channel is not actionable for scheduling.
        if item.channel == Channel.unknown:
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.UNSUPPORTED_CHANNEL,
                    message=f"experiment {item.id} has unsupported channel",
                    path=f"experiment_plan.items[{item.id}].channel",
                    suggested_fix="Use a concrete channel (youtube/tiktok/instagram/x).",
                )
            )

    # Any issue is treated as blocking for the golden path; pass only when clean.
    passed = not issues
    severity = ValidationSeverity.none if passed else ValidationSeverity.blocking
    retry = None if passed else "; ".join(i.message for i in issues)
    return ValidationReport(passed=passed, severity=severity, issues=issues, retry_instruction=retry)
