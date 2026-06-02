package com.launchpilot.dto.internal;

public record InternalAgentRunAcceptedResponse(
        boolean ok,
        String agentRunId,
        String status,
        String streamUrl,
        String snapshotUrl,
        String acceptedAt) {}
