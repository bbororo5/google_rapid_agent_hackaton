package com.launchpilot.dto.elastic;

import java.util.List;
import java.util.Map;

public record CampaignDoc(
        String campaignId,
        String workspaceId,
        String name,
        String description,
        List<String> primaryChannels,
        List<String> targetMetrics,
        Map<String, String> dateRange,
        String createdAt,
        String updatedAt,
        String brandName,
        List<String> goals,
        List<String> constraints) {}
