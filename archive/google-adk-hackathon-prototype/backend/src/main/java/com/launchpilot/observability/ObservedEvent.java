package com.launchpilot.observability;

import java.util.Map;

/**
 * A point-in-time event that should be queryable in logs or trace annotations.
 */
public record ObservedEvent(
        String name,
        ObservedStatus status,
        Map<String, Object> attributes) {

    public ObservedEvent {
        attributes = attributes == null ? Map.of() : Map.copyOf(attributes);
    }

    public static ObservedEvent of(String name, ObservedStatus status) {
        return new ObservedEvent(name, status, Map.of());
    }
}
