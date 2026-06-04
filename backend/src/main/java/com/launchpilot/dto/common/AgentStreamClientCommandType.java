package com.launchpilot.dto.common;

import com.fasterxml.jackson.annotation.JsonProperty;

/** 계약 01 asyncapi: 클라→서버 명령 타입. */
public enum AgentStreamClientCommandType {
    @JsonProperty("message.send") MESSAGE_SEND,
    @JsonProperty("connection.resume") CONNECTION_RESUME,
    @JsonProperty("connection.full_sync") CONNECTION_FULL_SYNC,
    @JsonProperty("run.cancel") RUN_CANCEL,
    @JsonProperty("approval.update_payload") APPROVAL_UPDATE_PAYLOAD,
    @JsonProperty("approval.approve") APPROVAL_APPROVE,
    @JsonProperty("approval.reject") APPROVAL_REJECT
}
