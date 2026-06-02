package com.launchpilot.dto.internal;

import com.fasterxml.jackson.annotation.JsonProperty;

/** 계약 02 asyncapi: Python→Java workflow 이벤트 타입 8종 (connection/대화/승인 제외). */
public enum AgentWorkflowEventType {
    @JsonProperty("run.started") RUN_STARTED,
    @JsonProperty("step.updated") STEP_UPDATED,
    @JsonProperty("observation.created") OBSERVATION_CREATED,
    @JsonProperty("signal.detected") SIGNAL_DETECTED,
    @JsonProperty("hypothesis.created") HYPOTHESIS_CREATED,
    @JsonProperty("experiment_plan.drafted") EXPERIMENT_PLAN_DRAFTED,
    @JsonProperty("run.cancelled") RUN_CANCELLED,
    @JsonProperty("run.failed") RUN_FAILED
}
