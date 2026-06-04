package com.launchpilot.dto.internal;

import java.util.List;
import java.util.Map;

public record InternalAgentTurnRequest(
        String threadId,
        String workspaceId,
        String campaignId,
        String content,
        List<Map<String, Object>> attachments,
        String clientCreatedAt,
        TraceContext traceContext) {}
