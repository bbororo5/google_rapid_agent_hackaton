package com.launchpilot.dto.common;

import com.fasterxml.jackson.annotation.JsonProperty;

/** 계약 01 asyncapi: 재접속 리플레이 범위 (소문자 직렬화). */
public enum ReplayScope {
    @JsonProperty("missed_events") MISSED_EVENTS,
    @JsonProperty("full_timeline") FULL_TIMELINE
}
