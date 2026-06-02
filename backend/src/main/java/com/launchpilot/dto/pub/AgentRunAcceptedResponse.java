package com.launchpilot.dto.pub;

public record AgentRunAcceptedResponse(
        boolean ok,
        String agentRunId,
        String status,
        String streamUrl,
        String nextPollUrl,
        String createdAt) {}
