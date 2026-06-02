package com.launchpilot.dto.common;

/** 계약 01 asyncapi: 세밀한 진행 단계 축 (WS step.stage). */
public enum AgentRunStage {
    IMPORT_METRICS,
    DETECT_PERFORMANCE_SIGNAL,
    GROUND_WITH_EVIDENCE,
    GENERATE_HYPOTHESIS,
    DRAFT_EXPERIMENT_PLAN,
    WAIT_FOR_APPROVAL,
    APPLY_APPROVED_PLAN
}
