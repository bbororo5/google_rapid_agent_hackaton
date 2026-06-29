package com.launchpilot.contracts.shared;

public record ToolCallLog(
        int sequence,
        String toolName,
        ToolCallStatus status,
        Integer durationMs,
        String errorMessage) {}
