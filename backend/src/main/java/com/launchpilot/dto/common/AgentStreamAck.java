package com.launchpilot.dto.common;

/** 계약 01 asyncapi: 클라 명령 접수 확인. */
public record AgentStreamAck(
        boolean ok,
        String commandId,
        String agentRunId,
        String acceptedAt) {}
