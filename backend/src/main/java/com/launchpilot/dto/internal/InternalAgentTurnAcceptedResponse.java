package com.launchpilot.dto.internal;

public record InternalAgentTurnAcceptedResponse(
        boolean ok,
        String threadId,
        String acceptedAt) {}
