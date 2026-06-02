package com.launchpilot.dto.common;

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

    Channel(String value) {
        this.value = value;
    }

    @JsonValue
    public String value() {
        return value;
    }

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
