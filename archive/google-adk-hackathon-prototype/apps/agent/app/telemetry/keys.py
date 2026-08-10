"""Standard metadata keys exposed by the Agent Core telemetry component."""

from __future__ import annotations

from enum import Enum


class TelemetryKey(str, Enum):
    """Stable metadata keys used by Agent Core spans and eval records."""

    THREAD_ID = "thread_id"
    REQUEST_ID = "request_id"
    TRACE_ID = "trace_id"
    TRACE_SOURCE = "trace_source"
    OTEL_TRACE_ID = "otel_trace_id"
    WORKSPACE_ID = "workspace_id"
    CAMPAIGN_ID = "campaign_id"
    GOAL = "goal"
    PHASE = "phase"
    STATUS = "status"
    STAGE = "stage"
    TOOL_NAME = "tool_name"
    VALIDATOR_PASSED = "validator_passed"
    BACKTRACK_COUNT = "backtrack_count"
    EVIDENCE_REF_COUNT = "evidence_ref_count"
    AGENT_SCOPE_WORKSPACE_ID = "agent.scope.workspace_id"
    AGENT_SCOPE_CAMPAIGN_ID = "agent.scope.campaign_id"
    AGENT_REPOSITORY_BACKEND = "agent.repository.backend"
    AGENT_REPOSITORY_CONFLICT = "agent.repository.conflict"
    AGENT_GOAL_KIND = "agent.goal.kind"
    AGENT_GOAL_BUDGET_PROFILE = "agent.goal.budget_profile"
    AGENT_GOAL_MAX_STEPS = "agent.goal.max_steps"
    AGENT_GOAL_MAX_LLM_CALLS = "agent.goal.max_llm_calls"
    AGENT_STATE_REVISION_BEFORE = "agent.state.revision_before"
    AGENT_STATE_REVISION_AFTER = "agent.state.revision_after"
    AGENT_STATE_DELTA_ID = "agent.state_delta.delta_id"
    AGENT_DELTA_INTENT = "agent.delta.intent"
    AGENT_DELTA_RESPONSE_MODE = "agent.delta.response_mode"
    AGENT_REDUCER_DECISION = "agent.reducer.decision"
    AGENT_DELEGATION_MODE = "agent.delegation.mode"
    AGENT_EPISODE_ID = "agent.episode.id"
    AGENT_EPISODE_OUTCOME = "agent.episode.outcome"
