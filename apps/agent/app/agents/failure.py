"""Failure policy for deterministic reviewer backtracking.

Two failure classes:
- Class 1 (tool/infra): retry cheaply, never call the LLM.
- Class 2 (reasoning / review fail): backtrack to the root-cause worker by issue
  code, reusing the successful prefix.
"""
from __future__ import annotations

from app.contracts import ValidationIssueCode

# Class 2 — issue code -> which worker is the root cause and must be re-run.
# A review fail does not always go back to the strategist; route by root cause.
ISSUE_TO_WORKER: dict[ValidationIssueCode, str] = {
    # Plan-shaped problems are the writer's to fix.
    ValidationIssueCode.MISSING_SUCCESS_CRITERIA: "writer",
    ValidationIssueCode.MISSING_SCHEDULE: "writer",
    ValidationIssueCode.EMPTY_EXPERIMENT_PLAN: "writer",
    ValidationIssueCode.UNSUPPORTED_CHANNEL: "writer",
    ValidationIssueCode.UNKNOWN_HYPOTHESIS_ID: "writer",
    # Reasoning/claim problems belong to the strategist.
    ValidationIssueCode.LOW_CONFIDENCE_WITHOUT_CAVEAT: "strategist",
    ValidationIssueCode.UNSAFE_OR_UNGROUNDED_CLAIM: "strategist",
    ValidationIssueCode.UNKNOWN_SIGNAL_ID: "strategist",
    # A hallucinated evidence ref must be fixed by whoever produced it.
    ValidationIssueCode.UNKNOWN_EVIDENCE_REF: "generator",  # analyst/strategist
    # Pure shape errors are handled by the deterministic formatter step.
    ValidationIssueCode.SCHEMA_INVALID: "formatter",
}

# When issues span multiple workers, restart from the EARLIEST in pipeline order
# so the later stages regenerate on top of the fix (prefix reuse, P1).
_WORKER_ORDER = ["analyst", "generator", "strategist", "writer", "formatter"]


def route(issue_codes: list[ValidationIssueCode]) -> str:
    """Pick the single root-cause worker to backtrack to."""
    targets = {ISSUE_TO_WORKER.get(c, "writer") for c in issue_codes}
    for worker in _WORKER_ORDER:
        if worker in targets:
            # "generator" maps onto the strategist re-run path in the orchestrator.
            return "strategist" if worker == "generator" else worker
    return "writer"


# Class 1 — tool error codes worth a cheap retry (no LLM). Other codes are
# permanent (INDEX_UNAVAILABLE, NO_EVIDENCE_FOUND, INVALID_TOOL_REQUEST).
RETRYABLE_TOOL_CODES = {"ESQL_FAILED", "SEARCH_FAILED", "MCP_TOOL_FAILED"}
