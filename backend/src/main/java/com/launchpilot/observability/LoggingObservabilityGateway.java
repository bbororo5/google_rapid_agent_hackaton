package com.launchpilot.observability;

import java.util.LinkedHashMap;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;

/**
 * Default observability adapter for the Java container.
 *
 * It keeps component code behind the ObservabilityGateway interface while
 * providing useful structured logs and correlation headers before an OTel
 * exporter is wired in.
 */
@Component
public class LoggingObservabilityGateway implements ObservabilityGateway {

    private static final Logger log = LoggerFactory.getLogger(LoggingObservabilityGateway.class);

    @Override
    public ObservationScope startOperation(ObservedOperation operation, CorrelationContext correlation) {
        return new LoggingObservationScope(operation, correlation);
    }

    @Override
    public DownstreamTraceContext downstreamTraceContext(CorrelationContext correlation) {
        Map<String, String> headers = new LinkedHashMap<>();
        putIfPresent(headers, "x-launchpilot-request-id", correlation.requestId());
        putIfPresent(headers, "x-launchpilot-trace-id", correlation.traceId());
        putIfPresent(headers, "x-launchpilot-thread-id", correlation.threadId());
        putIfPresent(headers, "x-launchpilot-workspace-id", correlation.workspaceId());
        putIfPresent(headers, "x-launchpilot-campaign-id", correlation.campaignId());
        return new DownstreamTraceContext(
                correlation.requestId(),
                DownstreamTraceContext.JAVA_BACKEND_SOURCE,
                correlation.traceId(),
                headers);
    }

    @Override
    public void recordEvent(ObservedEvent event, CorrelationContext correlation) {
        withCorrelation(correlation, () -> log.info(
                "observability event={} status={} attributes={}",
                event.name(), event.status(), event.attributes()));
    }

    @Override
    public void recordError(ObservedError error, CorrelationContext correlation) {
        withCorrelation(correlation, () -> log.warn(
                "observability error={} attributes={}",
                error.name(), error.attributes(), error.cause()));
    }

    private static void putIfPresent(Map<String, String> headers, String name, String value) {
        if (value != null && !value.isBlank()) {
            headers.put(name, value);
        }
    }

    private static void withCorrelation(CorrelationContext correlation, Runnable action) {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        bind(correlation);
        try {
            action.run();
        } finally {
            restore(previous);
        }
    }

    private static void bind(CorrelationContext correlation) {
        putMdc("request_id", correlation.requestId());
        putMdc("trace_id", correlation.traceId());
        putMdc("thread_id", correlation.threadId());
        putMdc("workspace_id", correlation.workspaceId());
        putMdc("campaign_id", correlation.campaignId());
        putMdc("component", correlation.component());
        putMdc("operation", correlation.operation());
    }

    private static void putMdc(String key, String value) {
        if (value == null || value.isBlank()) {
            MDC.remove(key);
            return;
        }
        MDC.put(key, value);
    }

    private static void restore(Map<String, String> previous) {
        if (previous == null) {
            MDC.clear();
            return;
        }
        MDC.setContextMap(previous);
    }

    private static final class LoggingObservationScope implements ObservationScope {

        private final ObservedOperation operation;
        private final CorrelationContext correlation;
        private final Map<String, String> previousMdc;
        private final long startedNanos;
        private boolean completed;

        private LoggingObservationScope(ObservedOperation operation, CorrelationContext correlation) {
            this.operation = operation;
            this.correlation = correlation;
            this.previousMdc = MDC.getCopyOfContextMap();
            this.startedNanos = System.nanoTime();
            bind(correlation);
            log.info("operation started name={} kind={} attributes={}",
                    operation.name(), operation.kind(), operation.attributes());
        }

        @Override
        public CorrelationContext correlation() {
            return correlation;
        }

        @Override
        public void markSuccess(Map<String, Object> attributes) {
            completed = true;
            log.info("operation succeeded name={} duration_ms={} attributes={}",
                    operation.name(), elapsedMillis(), safeAttributes(attributes));
        }

        @Override
        public void markFailure(Throwable error, Map<String, Object> attributes) {
            completed = true;
            log.warn("operation failed name={} duration_ms={} attributes={}",
                    operation.name(), elapsedMillis(), safeAttributes(attributes), error);
        }

        @Override
        public void close() {
            if (!completed) {
                log.info("operation closed name={} duration_ms={}", operation.name(), elapsedMillis());
            }
            restore(previousMdc);
        }

        private long elapsedMillis() {
            return (System.nanoTime() - startedNanos) / 1_000_000;
        }

        private Map<String, Object> safeAttributes(Map<String, Object> attributes) {
            return attributes == null ? Map.of() : Map.copyOf(attributes);
        }
    }
}
