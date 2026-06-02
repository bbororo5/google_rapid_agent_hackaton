package com.launchpilot.dto.common;

public record AgentStepSnapshot(
        String id,
        int order,
        AgentRunStage stage,
        AgentStepStatus status) {}
