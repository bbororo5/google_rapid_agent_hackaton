package com.launchpilot.dto.common;

import java.util.List;

public record Signal(
        String id,
        String type,
        String title,
        String description,
        String metricName,
        double currentValue,
        double baselineValue,
        double liftRatio,
        DateRange dateWindow,
        Confidence confidence,
        List<String> evidenceRefs) {}
