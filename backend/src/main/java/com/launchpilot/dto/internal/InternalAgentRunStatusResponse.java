package com.launchpilot.dto.internal;

import com.launchpilot.dto.common.AgentResultPayload;
import com.launchpilot.dto.common.AgentRunStatus;
import com.launchpilot.dto.common.ToolCallLog;
import java.util.List;

public record InternalAgentRunStatusResponse(
        String agentRunId,
        AgentRunStatus status,
        String currentStage,
        int retryCount,
        String errorMessage,
        AgentResultPayload payload,
        List<ToolCallLog> toolCallLogs,
        AgentDiagnostics agentDiagnostics,
        String startedAt,
        String updatedAt,
        String completedAt) {}
