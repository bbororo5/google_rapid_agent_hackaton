package com.launchpilot.dto.common;

import com.fasterxml.jackson.annotation.JsonProperty;

/** 계약 01 asyncapi: 클라→서버 명령 타입. */
public enum AgentStreamClientCommandType {
    @JsonProperty("message.send") MESSAGE_SEND
}
