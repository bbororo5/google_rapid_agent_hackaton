package com.launchpilot.api;

import com.launchpilot.dto.pub.ErrorResponse;
import com.launchpilot.service.ApiException;
import com.launchpilot.service.IdGenerator;
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

    public GlobalExceptionHandler(IdGenerator ids) {
        this.ids = ids;
    }

    @ExceptionHandler(ApiException.class)
    public ResponseEntity<ErrorResponse> handleApi(ApiException e) {
        return ResponseEntity.status(e.httpStatus())
                .body(ErrorResponse.of(e.code(), e.getMessage(), ids.newRequestId()));
    }

    @ExceptionHandler({
            MethodArgumentNotValidException.class,
            MissingServletRequestParameterException.class,
            MissingServletRequestPartException.class
    })
    public ResponseEntity<ErrorResponse> handleValidation(Exception e) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(ErrorResponse.of("INVALID_REQUEST", e.getMessage(), ids.newRequestId()));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleGeneric(Exception e) {
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(ErrorResponse.of("INTERNAL_ERROR", e.getMessage(), ids.newRequestId()));
    }
}
