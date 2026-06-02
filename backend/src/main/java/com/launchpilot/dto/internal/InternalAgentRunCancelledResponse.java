package com.launchpilot.dto.internal;

public record InternalAgentRunCancelledResponse(
        boolean ok,
        String agentRunId,
        String status,
        String cancelledAt) {}
