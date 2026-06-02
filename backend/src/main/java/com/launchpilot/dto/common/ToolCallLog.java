package com.launchpilot.dto.common;

public record ToolCallLog(
        int sequence,
        String toolName,
        ToolCallStatus status,
        Integer durationMs,
        String errorMessage) {}
