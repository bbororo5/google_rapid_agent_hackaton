package com.launchpilot.observability;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

final class W3cTraceContext {

    private W3cTraceContext() {
    }

    static String traceId(CorrelationContext correlation) {
        String seed = String.join(":",
                value(correlation.requestId()),
                value(correlation.threadId()),
                value(correlation.workspaceId()),
                value(correlation.campaignId()));
        String traceId = sha256Hex(seed).substring(0, 32);
        return "00000000000000000000000000000000".equals(traceId) ? "00000000000000000000000000000001" : traceId;
    }

    static String spanId(CorrelationContext correlation) {
        String seed = String.join(":",
                value(correlation.component()),
                value(correlation.operation()),
                value(correlation.requestId()),
                value(correlation.threadId()));
        String spanId = sha256Hex(seed).substring(0, 16);
        return "0000000000000000".equals(spanId) ? "0000000000000001" : spanId;
    }

    static String traceparent(String traceId, String spanId) {
        return "00-" + traceId + "-" + spanId + "-01";
    }

    private static String value(String value) {
        return value == null ? "" : value;
    }

    private static String sha256Hex(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] bytes = digest.digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder hex = new StringBuilder(bytes.length * 2);
            for (byte b : bytes) {
                hex.append(String.format("%02x", b));
            }
            return hex.toString();
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 is required by the Java runtime", e);
        }
    }
}
