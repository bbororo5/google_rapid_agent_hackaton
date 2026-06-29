package com.launchpilot.observability;

import java.util.Map;

/**
 * Trace and correlation payload passed from Java to downstream components.
 */
public record DownstreamTraceContext(
        String requestId,
        String source,
        String otelTraceId,
        Map<String, String> headers) {

    public static final String JAVA_BACKEND_SOURCE = "java-backend";

    public DownstreamTraceContext {
        headers = headers == null ? Map.of() : Map.copyOf(headers);
    }
}
