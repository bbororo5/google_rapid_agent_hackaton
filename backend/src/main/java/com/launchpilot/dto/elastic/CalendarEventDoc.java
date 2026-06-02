package com.launchpilot.dto.elastic;

import com.launchpilot.dto.common.Channel;

public record CalendarEventDoc(
        String eventId,
        String growthBriefId,
        String experimentId,
        String workspaceId,
        String campaignId,
        String title,
        Channel channel,
        String scheduledAt,
        String targetMetric,
        String successCriteria,
        String productionBrief,
        String createdAt) {}
