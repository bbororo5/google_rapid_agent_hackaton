package com.launchpilot.dto.pub;

/** 계약 01 openapi: 런 취소 응답 (status = CANCELLED). */
public record CancelAgentRunResponse(
        boolean ok,
        String agentRunId,
        String status,
        String cancelledAt) {}
