package com.launchpilot.dto.common;

/** 계약 enum (이름 그대로 직렬화). */
public enum AgentRunStatus {
    PENDING,
    RUNNING_SIGNAL_DETECTION,
    RUNNING_EVIDENCE_SEARCH,
    RUNNING_HYPOTHESIS_GENERATION,
    RUNNING_EXPERIMENT_GENERATION,
    WAITING_FOR_APPROVAL,
    SUCCESS,
    FAILED,
    CANCELLED
}
