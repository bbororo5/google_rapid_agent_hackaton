package com.launchpilot.observability;

/**
 * Request and domain identifiers shared by logs, metrics, traces, and
 * Java-to-Python propagation.
 */
public record CorrelationContext(
        String requestId,
        String threadId,
        String workspaceId,
        String campaignId,
        String component,
        String operation) {

    public CorrelationContext withComponent(String nextComponent) {
        return new CorrelationContext(
                requestId,
                threadId,
                workspaceId,
                campaignId,
                nextComponent,
                operation);
    }

    public CorrelationContext withOperation(String nextOperation) {
        return new CorrelationContext(
                requestId,
                threadId,
                workspaceId,
                campaignId,
                component,
                nextOperation);
    }
}
