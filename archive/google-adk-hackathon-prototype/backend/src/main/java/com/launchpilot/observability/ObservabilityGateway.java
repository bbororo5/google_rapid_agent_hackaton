package com.launchpilot.observability;

/**
 * Java container observability boundary.
 *
 * Domain components use this interface to describe what happened. Concrete
 * implementations decide how that becomes logs, metrics, traces, MDC, and
 * Google Cloud Operations export.
 */
public interface ObservabilityGateway {

    /**
     * Start an observed operation and bind its correlation context for the scope.
     *
     * @param operation the operation being observed
     * @param correlation request/thread/workspace identifiers for log and trace correlation
     * @return a scope that must be closed when the operation ends
     */
    ObservationScope startOperation(ObservedOperation operation, CorrelationContext correlation);

    /**
     * Build trace/correlation data to propagate to a downstream component.
     *
     * The first downstream user is Python Agent Core. Implementations may add
     * W3C trace headers and a LaunchPilot trace context without exposing OTel
     * details to business components.
     */
    DownstreamTraceContext downstreamTraceContext(CorrelationContext correlation);

    /**
     * Record a point-in-time domain event inside the current request flow.
     */
    void recordEvent(ObservedEvent event, CorrelationContext correlation);

    /**
     * Record an error with the current request flow.
     */
    void recordError(ObservedError error, CorrelationContext correlation);
}
