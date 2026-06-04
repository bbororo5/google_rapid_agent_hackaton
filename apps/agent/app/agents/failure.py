"""Failure policy (agent-tool-spec §4).

Two failure classes:
- Class 1 (tool/infra): retry cheaply, never call the LLM.
- Class 2 (reasoning / review fail): backtrack to the root-cause worker by issue
  code, reusing the successful prefix.
"""
from __future__ import annotations

from app.contracts import ValidationIssueCode

# Class 2 — issue code -> which worker to re-run.
ISSUE_TO_WORKER: dict[ValidationIssueCode, str] = {
    ValidationIssueCode.MISSING_SUCCESS_CRITERIA: "writer",
    ValidationIssueCode.MISSING_SCHEDULE: "writer",
    ValidationIssueCode.EMPTY_EXPERIMENT_PLAN: "writer",
    ValidationIssueCode.UNSUPPORTED_CHANNEL: "writer",
    ValidationIssueCode.UNKNOWN_HYPOTHESIS_ID: "writer",
    ValidationIssueCode.LOW_CONFIDENCE_WITHOUT_CAVEAT: "strategist",
    ValidationIssueCode.UNSAFE_OR_UNGROUNDED_CLAIM: "strategist",
    ValidationIssueCode.UNKNOWN_SIGNAL_ID: "strategist",
    ValidationIssueCode.UNKNOWN_EVIDENCE_REF: "generator",  # analyst/strategist
    ValidationIssueCode.SCHEMA_INVALID: "formatter",
}

# Earliest worker in the pipeline order wins when issues span workers.
_WORKER_ORDER = ["analyst", "generator", "strategist", "writer", "formatter"]


def route(issue_codes: list[ValidationIssueCode]) -> str:
    """Pick the single root-cause worker to backtrack to."""
    targets = {ISSUE_TO_WORKER.get(c, "writer") for c in issue_codes}
    for worker in _WORKER_ORDER:
        if worker in targets:
            return "strategist" if worker == "generator" else worker
    return "writer"


# Class 1 — tool error codes that are worth a cheap retry (no LLM).
RETRYABLE_TOOL_CODES = {"ESQL_FAILED", "SEARCH_FAILED", "MCP_TOOL_FAILED"}
