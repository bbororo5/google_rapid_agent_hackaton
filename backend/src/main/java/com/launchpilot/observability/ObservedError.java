package com.launchpilot.observability;

import java.util.Map;

/**
 * Compact error report for the observability boundary.
 */
public record ObservedError(
        String name,
        Throwable cause,
        Map<String, Object> attributes) {

    public ObservedError {
        attributes = attributes == null ? Map.of() : Map.copyOf(attributes);
    }
}
