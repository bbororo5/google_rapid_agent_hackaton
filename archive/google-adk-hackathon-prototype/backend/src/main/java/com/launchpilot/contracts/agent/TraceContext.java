package com.launchpilot.contracts.agent;

public record TraceContext(
        String requestId,
        String source,
        String otelTraceId) {}
