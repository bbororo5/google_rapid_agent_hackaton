"""Reviewer gate — deterministic set-based validation (no LLM).

Checks the assembled payload against the contract issue codes (05): mechanical
cross-id integrity, required fields, and operational schedulability. A failing
report blocks the planning round; it cannot be overturned by any LLM critique.
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


def review(payload: AgentResultPayload) -> ValidationReport:
    issues: list[ValidationIssue] = []
    # Build the id sets we cross-check references against.
    signal_ids = {s.id for s in payload.signals}
    hypothesis_ids = {h.id for h in payload.hypotheses}
    # Union of refs the tools actually grounded (used as a soft allow-list).
    grounded_refs = {r for s in payload.signals for r in s.evidence_refs}
    for h in payload.hypotheses:
        grounded_refs.update(h.supporting_evidence_refs)

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

    # Any issue is treated as blocking for the planning approval gate.
    passed = not issues
    severity = ValidationSeverity.none if passed else ValidationSeverity.blocking
    retry = None if passed else "; ".join(i.message for i in issues)
    return ValidationReport(passed=passed, severity=severity, issues=issues, retry_instruction=retry)
