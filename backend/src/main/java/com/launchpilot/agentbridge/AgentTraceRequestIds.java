package com.launchpilot.agentbridge;

final class AgentTraceRequestIds {

    private AgentTraceRequestIds() {
    }

    static String normalize(String requestId, String fallbackThreadId) {
        String raw = requestId == null || requestId.isBlank() ? fallbackThreadId : requestId;
        String normalized = raw.replaceAll("[^A-Za-z0-9_]", "_");
        return normalized.startsWith("req_") ? normalized : "req_" + normalized;
    }
}
