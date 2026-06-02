package com.launchpilot.dto.internal;

import com.fasterxml.jackson.annotation.JsonProperty;

/** 계약 02 asyncapi: Java→Python 명령 타입 (현재 cancel만). */
public enum InternalAgentCommandType {
    @JsonProperty("run.cancel") RUN_CANCEL
}
