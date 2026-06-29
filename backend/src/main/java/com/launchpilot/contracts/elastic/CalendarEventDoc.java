package com.launchpilot.contracts.elastic;

import com.launchpilot.contracts.shared.Channel;

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
