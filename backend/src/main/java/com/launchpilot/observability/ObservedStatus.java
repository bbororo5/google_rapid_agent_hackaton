package com.launchpilot.observability;

/**
 * Normalized status values for events and operation outcomes.
 */
public enum ObservedStatus {
    STARTED,
    SUCCEEDED,
    FAILED,
    CANCELLED,
    SKIPPED
}
