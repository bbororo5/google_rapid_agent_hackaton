package com.launchpilot.dto.common;

import java.util.List;

public record ExperimentPlan(
        String id,
        String summary,
        Confidence overallConfidence,
        List<ExperimentItem> items) {}
