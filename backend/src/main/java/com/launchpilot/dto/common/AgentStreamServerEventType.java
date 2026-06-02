package com.launchpilot.dto.common;

import com.fasterxml.jackson.annotation.JsonProperty;

/** 계약 01 asyncapi: 서버→클라 이벤트 타입 22종 (connection 6 + 대화 2 + 런 14). */
public enum AgentStreamServerEventType {
    @JsonProperty("connection.resume_accepted") CONNECTION_RESUME_ACCEPTED,
    @JsonProperty("connection.replay_started") CONNECTION_REPLAY_STARTED,
    @JsonProperty("connection.replay_completed") CONNECTION_REPLAY_COMPLETED,
    @JsonProperty("connection.full_sync_required") CONNECTION_FULL_SYNC_REQUIRED,
    @JsonProperty("connection.reauth_required") CONNECTION_REAUTH_REQUIRED,
    @JsonProperty("connection.session_expired") CONNECTION_SESSION_EXPIRED,
    @JsonProperty("run.started") RUN_STARTED,
    @JsonProperty("step.updated") STEP_UPDATED,
    @JsonProperty("user.message.created") USER_MESSAGE_CREATED,
    @JsonProperty("assistant.message.created") ASSISTANT_MESSAGE_CREATED,
    @JsonProperty("observation.created") OBSERVATION_CREATED,
    @JsonProperty("tool.updated") TOOL_UPDATED,
    @JsonProperty("signal.detected") SIGNAL_DETECTED,
    @JsonProperty("hypothesis.created") HYPOTHESIS_CREATED,
    @JsonProperty("experiment_plan.drafted") EXPERIMENT_PLAN_DRAFTED,
    @JsonProperty("approval.requested") APPROVAL_REQUESTED,
    @JsonProperty("approval.committed") APPROVAL_COMMITTED,
    @JsonProperty("run.paused") RUN_PAUSED,
    @JsonProperty("run.resumed") RUN_RESUMED,
    @JsonProperty("run.cancelled") RUN_CANCELLED,
    @JsonProperty("run.completed") RUN_COMPLETED,
    @JsonProperty("run.failed") RUN_FAILED
}
