package com.launchpilot.common;

/** 도메인 오류 -> HTTP 상태 + 계약 에러 코드 매핑. */
public class ApiException extends RuntimeException {

    private final int httpStatus;
    private final String code;

    /**
     * Create an ApiException that carries an HTTP status, a domain error code, and an exception message.
     *
     * @param httpStatus the HTTP status code to expose for this error
     * @param code       the domain/contract error code to expose
     * @param message    the exception message stored in the underlying RuntimeException
     */
    public ApiException(int httpStatus, String code, String message) {
        super(message);
        this.httpStatus = httpStatus;
        this.code = code;
    }

    /**
     * HTTP status code associated with this API exception.
     *
     * @return the HTTP status code to expose
     */
    public int httpStatus() {
        return httpStatus;
    }

    /**
     * Retrieve the contract/domain error code associated with this exception.
     *
     * @return the contract error code string exposed for the API (e.g., "RUN_NOT_FOUND")
     */
    public String code() {
        return code;
    }

    /**
     * Create an ApiException for a missing run with HTTP status 404 and code "RUN_NOT_FOUND".
     *
     * @param message the exception message to expose
     * @return an ApiException with HTTP status 404 and error code "RUN_NOT_FOUND"
     */
    public static ApiException notFound(String message) {
        return new ApiException(404, "RUN_NOT_FOUND", message);
    }

    /**
     * Create an ApiException for HTTP 400 (Bad Request) with the contract error code "INVALID_REQUEST".
     *
     * @param message the error message to include in the exception
     * @return an ApiException with HTTP status 400 and code "INVALID_REQUEST"
     */
    public static ApiException badRequest(String message) {
        return new ApiException(400, "INVALID_REQUEST", message);
    }

    /**
     * Create an ApiException representing an HTTP 409 Conflict for duplicate run IDs.
     *
     * @param message detail message describing the conflict
     * @return ApiException with HTTP status 409 and code `RUN_ID_CONFLICT`
     */
    public static ApiException conflict(String message) {
        return new ApiException(409, "RUN_ID_CONFLICT", message);
    }

    /**
     * Create an ApiException representing an internal server error.
     *
     * @param message the exception message to expose
     * @return the ApiException with HTTP status 500 and error code "INTERNAL_AGENT_ERROR"
     */
    public static ApiException internal(String message) {
        return new ApiException(500, "INTERNAL_AGENT_ERROR", message);
    }
}
