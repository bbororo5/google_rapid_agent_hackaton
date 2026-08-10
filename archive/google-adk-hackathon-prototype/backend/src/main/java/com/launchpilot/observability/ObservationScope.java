package com.launchpilot.observability;

import java.util.Map;

/**
 * Lifetime handle for one observed operation.
 *
 * Business code should use this as a try-with-resources boundary. The concrete
 * implementation may close spans, clear MDC, stop timers, or flush metrics.
 */
public interface ObservationScope extends AutoCloseable {

    /**
     * Correlation values bound to this operation.
     */
    CorrelationContext correlation();

    /**
     * Mark the operation as successful and attach a compact result summary.
     */
    void markSuccess(Map<String, Object> attributes);

    /**
     * Mark the operation as failed and attach a compact error summary.
     */
    void markFailure(Throwable error, Map<String, Object> attributes);

    /**
     * End the observed operation.
     */
    @Override
    void close();
}
