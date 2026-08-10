package com.launchpilot.contracts.shared;

public record ExperimentItem(
        String id,
        String hypothesisId,
        String title,
        Channel channel,
        String contentFormat,
        String hook,
        String cta,
        String targetMetric,
        String successCriteria,
        String scheduledAt,
        String productionBrief) {}
