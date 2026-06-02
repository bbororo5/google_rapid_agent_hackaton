package com.launchpilot.dto.internal;

public record AgentDiagnostics(
        String worker,
        Boolean validatorPassed,
        int backtrackCount,
        boolean phoenixReflectionUsed,
        String traceId) {}
