package com.launchpilot.contracts.elastic;

import com.launchpilot.contracts.shared.ExperimentItem;
import com.launchpilot.contracts.shared.Hypothesis;
import com.launchpilot.contracts.shared.Signal;
import java.util.List;

public record GrowthBriefDoc(
        String growthBriefId,
        String workspaceId,
        String campaignId,
        String threadId,
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
