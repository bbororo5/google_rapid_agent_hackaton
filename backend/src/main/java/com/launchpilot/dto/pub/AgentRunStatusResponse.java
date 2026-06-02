package com.launchpilot.dto.pub;

import com.launchpilot.dto.common.AgentResultPayload;
import com.launchpilot.dto.common.AgentRunStatus;
import com.launchpilot.dto.common.ToolCallLog;
import java.util.List;

public record AgentRunStatusResponse(
        String agentRunId,
        AgentRunStatus status,
        String currentStage,
        int retryCount,
        String errorMessage,
        AgentResultPayload payload,
        List<ToolCallLog> toolCallLogs) {}
