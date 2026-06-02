package com.launchpilot.dto.common;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

/** 계약 enum: low, medium, medium_high, high */
public enum Confidence {
    LOW("low"),
    MEDIUM("medium"),
    MEDIUM_HIGH("medium_high"),
    HIGH("high");

    private final String value;

    /**
     * Initializes the enum constant with its serialized string representation.
     *
     * @param value the lowercase/string form used for serialization
     */
    Confidence(String value) {
        this.value = value;
    }

    /**
     * Provide the enum's serialized string representation for JSON.
     *
     * @return the stored string value mapped to this enum constant
     */
    @JsonValue
    public String value() {
        return value;
    }

    /**
     * Create a Confidence enum from its serialized string value.
     *
     * @param raw the serialized value to convert (one of "low", "medium", "medium_high", "high")
     * @return the matching Confidence constant
     * @throws IllegalArgumentException if {@code raw} does not match any Confidence value
     */
    @JsonCreator
    public static Confidence from(String raw) {
        for (Confidence c : values()) {
            if (c.value.equals(raw)) {
                return c;
            }
        }
        throw new IllegalArgumentException("invalid confidence: " + raw);
    }
}
