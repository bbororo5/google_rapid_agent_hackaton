package com.launchpilot.dto.internal;

/** 계약 02 asyncapi: Java가 Python 내부 스트림으로 보내는 운영 명령. */
public record InternalAgentCommand(
        String commandId,
        InternalAgentCommandType type,
        String agentRunId,
        String reason) {}
