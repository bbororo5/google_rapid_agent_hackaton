package com.launchpilot.contracts.shared;

import java.util.List;

public record Hypothesis(
        String id,
        List<String> signalIds,
        String statement,
        String rationale,
        Confidence confidence,
        List<String> supportingEvidenceRefs,
        List<String> caveats) {}
