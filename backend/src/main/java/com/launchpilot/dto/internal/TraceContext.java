package com.launchpilot.dto.internal;

public record TraceContext(
        String requestId,
        String source,
        String otelTraceId) {}
