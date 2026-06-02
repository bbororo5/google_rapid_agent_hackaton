package com.launchpilot.dto.common;

/** 계약 01 asyncapi: Java가 WAITING_FOR_APPROVAL 도달 시 합성하는 승인 게이트. approval_id = appr_*. */
public record ApprovalGateRequest(
        String approvalId,
        ApprovalGateKind gate,
        AgentResultPayload payload) {}
