package com.launchpilot.service;

/** 도메인 오류 -> HTTP 상태 + 계약 에러 코드 매핑. */
public class ApiException extends RuntimeException {

    private final int httpStatus;
    private final String code;

    public ApiException(int httpStatus, String code, String message) {
        super(message);
        this.httpStatus = httpStatus;
        this.code = code;
    }

    public int httpStatus() {
        return httpStatus;
    }

    public String code() {
        return code;
    }

    public static ApiException notFound(String message) {
        return new ApiException(404, "RUN_NOT_FOUND", message);
    }

    public static ApiException badRequest(String message) {
        return new ApiException(400, "INVALID_REQUEST", message);
    }

    public static ApiException conflict(String message) {
        return new ApiException(409, "RUN_ID_CONFLICT", message);
    }

    public static ApiException internal(String message) {
        return new ApiException(500, "INTERNAL_AGENT_ERROR", message);
    }
}
