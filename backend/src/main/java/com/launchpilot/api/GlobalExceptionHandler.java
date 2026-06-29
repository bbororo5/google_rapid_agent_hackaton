package com.launchpilot.api;

import com.launchpilot.contracts.frontend.ErrorResponse;
import com.launchpilot.common.ApiException;
import com.launchpilot.common.IdGenerator;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.support.MissingServletRequestPartException;

/** 모든 오류를 계약 ErrorResponse {ok:false, error:{code, message, request_id}} 로 변환. */
@RestControllerAdvice
public class GlobalExceptionHandler {

    private final IdGenerator ids;

    /**
     * Create a GlobalExceptionHandler that uses the provided IdGenerator to generate per-error request IDs.
     *
     * @param ids generator used to produce `request_id` values included in ErrorResponse objects
     */
    public GlobalExceptionHandler(IdGenerator ids) {
        this.ids = ids;
    }

    /**
     * Translate an ApiException into a standardized HTTP error response.
     *
     * @param e the ApiException thrown by a controller
     * @return a ResponseEntity whose status equals the exception's HTTP status and whose body is an ErrorResponse containing the exception's code, the exception message, and a generated request_id
     */
    @ExceptionHandler(ApiException.class)
    public ResponseEntity<ErrorResponse> handleApi(ApiException e) {
        return ResponseEntity.status(e.httpStatus())
                .body(ErrorResponse.of(e.code(), e.getMessage(), ids.newRequestId()));
    }

    /**
     * Handle validation and missing-request errors and convert them into a standardized error response.
     *
     * @param e the caught validation or missing-request exception (e.g., MethodArgumentNotValidException,
     *          MissingServletRequestParameterException, MissingServletRequestPartException)
     * @return a ResponseEntity with HTTP status 400 (Bad Request) whose body is an ErrorResponse with
     *         code "INVALID_REQUEST", the exception's message, and a generated request_id
     */
    @ExceptionHandler({
            MethodArgumentNotValidException.class,
            MissingServletRequestParameterException.class,
            MissingServletRequestPartException.class
    })
    public ResponseEntity<ErrorResponse> handleValidation(Exception e) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(ErrorResponse.of("INVALID_REQUEST", e.getMessage(), ids.newRequestId()));
    }

    /**
     * Handle uncaught exceptions and convert them into a standardized internal-server-error response.
     *
     * @param e the exception that was thrown; its message is used as the error message in the response
     * @return a ResponseEntity with HTTP status 500 and an ErrorResponse containing code `"INTERNAL_ERROR"`, the exception message, and a generated `request_id`
     */
    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleGeneric(Exception e) {
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(ErrorResponse.of("INTERNAL_ERROR", e.getMessage(), ids.newRequestId()));
    }
}
