package com.launchpilot.dto.pub;

import java.util.Map;

public record ErrorResponse(boolean ok, ErrorBody error) {

    public record ErrorBody(
            String code,
            String message,
            Map<String, Object> details,
            String requestId) {}

    public static ErrorResponse of(String code, String message, String requestId) {
        return new ErrorResponse(false, new ErrorBody(code, message, null, requestId));
    }
}
