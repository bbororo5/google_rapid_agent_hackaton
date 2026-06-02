package com.launchpilot.dto.elastic;

import com.launchpilot.dto.common.ExperimentItem;
import com.launchpilot.dto.common.Hypothesis;
import com.launchpilot.dto.common.Signal;
import java.util.List;

public record GrowthBriefDoc(
        String growthBriefId,
        String workspaceId,
        String campaignId,
        String agentRunId,
        String experimentPlanId,
        String approvedBy,
        String approvedAt,
        String summary,
        List<Signal> signals,
        List<Hypothesis> hypotheses,
        List<ExperimentItem> finalExperiments,
        List<String> sourceEvidenceRefs,
        List<String> calendarEventIds,
        int version,
        String createdAt) {}
