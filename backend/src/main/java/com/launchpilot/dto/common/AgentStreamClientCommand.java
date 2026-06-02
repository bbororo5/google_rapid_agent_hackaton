package com.launchpilot.dto.common;

import java.util.List;

/**
 * 계약 01 asyncapi: 클라→서버 명령 (resume/full_sync/runtime oneOf의 합집합 표현).
 * type에 따라 사용되는 필드가 다르며 나머지는 null.
 * command_id는 멱등 키 — 서버는 동일 command_id를 최대 1회만 실행한다.
 */
public record AgentStreamClientCommand(
        String commandId,
        AgentStreamClientCommandType type,
        String clientId,
        String sessionId,
        String agentRunId,
        Long lastReceivedSequence,
        String approvalId,
        List<ExperimentItem> finalExperiments,
        String reason) {}
