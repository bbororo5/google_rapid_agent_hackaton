package com.launchpilot.contracts.agent;

public record InternalAgentTurnAcceptedResponse(
        boolean ok,
        String threadId,
        String acceptedAt) {}
