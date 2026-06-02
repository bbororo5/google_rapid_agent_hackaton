package com.launchpilot.dto.common;

import com.fasterxml.jackson.annotation.JsonProperty;

/** 계약 01 asyncapi: glass-box observation 종류 (소문자 직렬화). */
public enum AgentObservationKind {
    @JsonProperty("progress") PROGRESS,
    @JsonProperty("evidence") EVIDENCE,
    @JsonProperty("signal") SIGNAL,
    @JsonProperty("hypothesis") HYPOTHESIS,
    @JsonProperty("plan") PLAN,
    @JsonProperty("warning") WARNING
}
