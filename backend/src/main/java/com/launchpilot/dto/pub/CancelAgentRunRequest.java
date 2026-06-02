package com.launchpilot.dto.pub;

/** 계약 01 openapi: 런 취소 요청 (WS run.cancel의 REST fallback). reason optional. */
public record CancelAgentRunRequest(
        String reason) {}
