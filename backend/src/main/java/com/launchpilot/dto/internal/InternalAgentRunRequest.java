package com.launchpilot.dto.internal;

import com.launchpilot.dto.common.DateRange;

public record InternalAgentRunRequest(
        String agentRunId,
        String workspaceId,
        String campaignId,
        String question,
        DateRange dateRange,
        String parentBriefId,
        TraceContext traceContext) {}
