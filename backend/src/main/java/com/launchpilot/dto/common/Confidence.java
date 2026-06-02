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

    Confidence(String value) {
        this.value = value;
    }

    @JsonValue
    public String value() {
        return value;
    }

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
