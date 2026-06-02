package com.launchpilot.dto.common;

import java.util.List;

public record AgentResultPayload(
        List<Signal> signals,
        List<Hypothesis> hypotheses,
        ExperimentPlan experimentPlan) {}
