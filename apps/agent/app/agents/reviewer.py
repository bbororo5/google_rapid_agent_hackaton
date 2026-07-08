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
                        message=f"가설 {h.id}가 존재하지 않는 신호 {sid}를 참조합니다",
                        path=f"hypotheses[{h.id}].signal_ids",
                        suggested_fix="분석가가 생성한 신호 id를 참조하세요.",
                    )
                )
        # Low/medium confidence claims must be hedged with a caveat.
        if h.confidence in _LOW_CONFIDENCE and not h.caveats:
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.LOW_CONFIDENCE_WITHOUT_CAVEAT,
                    message=f"가설 {h.id}는 확신도가 낮은데 주의사항(caveat)이 없습니다",
                    path=f"hypotheses[{h.id}].caveats",
                    suggested_fix="낮음/중간 확신도에는 주의사항을 1개 이상 추가하세요.",
                )
            )

    # --- Experiment plan checks ---
    plan = payload.experiment_plan
    if not plan.items:
        issues.append(
            ValidationIssue(
                code=ValidationIssueCode.EMPTY_EXPERIMENT_PLAN,
                message="실험 계획에 항목이 없습니다",
                path="experiment_plan.items",
                suggested_fix="실험 항목을 1개 이상 추가하세요.",
            )
        )
    for item in plan.items:
        # Each experiment must trace back to a real hypothesis.
        if item.hypothesis_id not in hypothesis_ids:
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.UNKNOWN_HYPOTHESIS_ID,
                    message=f"실험 {item.id}가 존재하지 않는 가설 {item.hypothesis_id}를 참조합니다",
                    path=f"experiment_plan.items[{item.id}].hypothesis_id",
                    suggested_fix="전략가가 생성한 가설 id를 참조하세요.",
                )
            )
        # Required operational fields must be non-empty.
        if not item.success_criteria.strip():
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.MISSING_SUCCESS_CRITERIA,
                    message=f"실험 {item.id}에 success_criteria가 없습니다",
                    path=f"experiment_plan.items[{item.id}].success_criteria",
                    suggested_fix="측정 가능한 성공 기준을 추가하세요.",
                )
            )
        if not item.scheduled_at.strip():
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.MISSING_SCHEDULE,
                    message=f"실험 {item.id}에 scheduled_at이 없습니다",
                    path=f"experiment_plan.items[{item.id}].scheduled_at",
                    suggested_fix="실행 예정 일시를 추가하세요.",
                )
            )
        # "unknown" channel is not actionable for scheduling.
        if item.channel == Channel.unknown:
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.UNSUPPORTED_CHANNEL,
                    message=f"실험 {item.id}의 채널이 지원되지 않습니다",
                    path=f"experiment_plan.items[{item.id}].channel",
                    suggested_fix="구체적인 채널(youtube/tiktok/instagram/x)을 사용하세요.",
                )
            )

    # Any issue is treated as blocking for the planning approval gate.
    passed = not issues
    severity = ValidationSeverity.none if passed else ValidationSeverity.blocking
    retry = None if passed else "; ".join(i.message for i in issues)
    return ValidationReport(passed=passed, severity=severity, issues=issues, retry_instruction=retry)
