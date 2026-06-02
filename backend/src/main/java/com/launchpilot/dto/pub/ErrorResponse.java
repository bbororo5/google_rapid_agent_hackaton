package com.launchpilot.dto.pub;

import java.util.Map;

public record ErrorResponse(boolean ok, ErrorBody error) {

    public record ErrorBody(
            String code,
            String message,
            Map<String, Object> details,
            String requestId) {}

    /**
     * Create an ErrorResponse representing a failed operation using the provided error data.
     *
     * @param code      the error code
     * @param message   a human-readable error message
     * @param requestId the request identifier associated with the error
     * @return an ErrorResponse with `ok` set to `false` and an ErrorBody containing the given `code`, `message`, `requestId`; the ErrorBody's `details` is `null`
     */
    public static ErrorResponse of(String code, String message, String requestId) {
        return new ErrorResponse(false, new ErrorBody(code, message, null, requestId));
    }
}
