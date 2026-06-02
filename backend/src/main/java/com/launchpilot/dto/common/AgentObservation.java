package com.launchpilot.dto.common;

import java.util.List;

public record AgentObservation(
        String id,
        AgentObservationKind kind,
        String title,
        String summary,
        List<String> evidenceRefs) {}
