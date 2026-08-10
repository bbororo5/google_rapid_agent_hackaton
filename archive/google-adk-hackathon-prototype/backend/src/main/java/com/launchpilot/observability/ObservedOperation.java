package com.launchpilot.observability;

import java.util.Map;

/**
 * A timed operation worth representing as a trace span and/or metric sample.
 */
public record ObservedOperation(
        String name,
        OperationKind kind,
        Map<String, Object> attributes) {

    public ObservedOperation {
        attributes = attributes == null ? Map.of() : Map.copyOf(attributes);
    }

    public static ObservedOperation of(String name, OperationKind kind) {
        return new ObservedOperation(name, kind, Map.of());
    }
}
