package com.launchpilot.dto.common;

/**
 * 계약 01 asyncapi: 서버→클라 단일 이벤트 봉투.
 * 타입별로 채워지는 필드가 다르며 나머지는 null (계약상 nullable).
 * connection.* 제어 이벤트는 sequence/agent_run_id를 생략할 수 있다.
 */
public record AgentStreamServerEvent(
        String eventId,
        AgentStreamServerEventType type,
        String agentRunId,
        String sessionId,
        Long sequence,
        String occurredAt,
        AgentRunStatus status,
        ReplayScope replayScope,
        Long lastReplayedSequence,
        Long nextExpectedSequence,
        AgentStepSnapshot step,
        AgentMessage message,
        AgentObservation observation,
        ToolCallLog toolCall,
        AgentResultPayload payload,
        ApprovalCommitResult approvalResult,
        ApprovalGateRequest approval,
        String errorMessage) {}
