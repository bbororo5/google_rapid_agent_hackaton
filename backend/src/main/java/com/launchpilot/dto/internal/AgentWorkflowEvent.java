package com.launchpilot.dto.internal;

import com.launchpilot.dto.common.AgentObservation;
import com.launchpilot.dto.common.AgentResultPayload;
import com.launchpilot.dto.common.AgentRunStatus;
import com.launchpilot.dto.common.AgentStepSnapshot;

/** 계약 02 asyncapi: Python이 Java로 스트리밍하는 user-safe workflow 이벤트. */
public record AgentWorkflowEvent(
        String eventId,
        AgentWorkflowEventType type,
        String agentRunId,
        int sequence,
        String occurredAt,
        AgentRunStatus status,
        AgentStepSnapshot step,
        AgentObservation observation,
        AgentResultPayload payload,
        String errorMessage) {}
