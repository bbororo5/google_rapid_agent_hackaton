package com.launchpilot.contracts.shared;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

/** 계약 enum: youtube, tiktok, instagram, x, unknown */
public enum Channel {
    YOUTUBE("youtube"),
    TIKTOK("tiktok"),
    INSTAGRAM("instagram"),
    X("x"),
    UNKNOWN("unknown");

    private final String value;

    /**
     * Constructs a Channel enum constant and assigns its serialized/raw string value.
     *
     * @param value the serialized representation to associate with this enum constant
     */
    Channel(String value) {
        this.value = value;
    }

    /**
     * Get the serialized string representation for this enum constant.
     *
     * @return the stored raw string used to serialize this enum constant (used by JSON serialization)
     */
    @JsonValue
    public String value() {
        return value;
    }

    /**
     * Converts a raw channel string into the corresponding Channel enum constant.
     *
     * @param raw the serialized/raw channel value to parse (e.g., "youtube", "tiktok")
     * @return the matching Channel constant
     * @throws IllegalArgumentException if the input does not match any Channel value
     */
    @JsonCreator
    public static Channel from(String raw) {
        for (Channel c : values()) {
            if (c.value.equals(raw)) {
                return c;
            }
        }
        throw new IllegalArgumentException("invalid channel: " + raw);
    }
}
