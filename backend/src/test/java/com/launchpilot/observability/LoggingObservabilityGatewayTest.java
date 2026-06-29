package com.launchpilot.observability;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;

class LoggingObservabilityGatewayTest {

    private final LoggingObservabilityGateway gateway = new LoggingObservabilityGateway();

    @AfterEach
    void clearMdc() {
        MDC.clear();
    }

    @Test
    void bindsAndRestoresMdcForOperationScope() {
        MDC.put("request_id", "req_existing");

        ObservationScope scope = gateway.startOperation(
                ObservedOperation.of("conversation.command", OperationKind.WEBSOCKET_MESSAGE),
                correlation());

        assertThat(MDC.get("request_id")).isEqualTo("req_1");
        assertThat(MDC.get("trace_id")).isEqualTo("trace_1");
        assertThat(MDC.get("thread_id")).isEqualTo("thread_1");
        assertThat(MDC.get("workspace_id")).isEqualTo("workspace_1");
        assertThat(MDC.get("campaign_id")).isEqualTo("campaign_1");
        assertThat(MDC.get("component")).isEqualTo("conversation");
        assertThat(MDC.get("operation")).isEqualTo("handle_command");

        scope.markSuccess(Map.of("handled", true));
        scope.close();

        assertThat(MDC.get("request_id")).isEqualTo("req_existing");
        assertThat(MDC.get("trace_id")).isNull();
    }

    @Test
    void createsDownstreamTraceHeaders() {
        DownstreamTraceContext downstream = gateway.downstreamTraceContext(correlation());

        assertThat(downstream.requestId()).isEqualTo("req_1");
        assertThat(downstream.source()).isEqualTo(DownstreamTraceContext.JAVA_BACKEND_SOURCE);
        assertThat(downstream.otelTraceId()).matches("^[a-f0-9]{32}$");
        assertThat(downstream.headers()).containsEntry("x-launchpilot-request-id", "req_1");
        assertThat(downstream.headers()).containsEntry("x-launchpilot-trace-id", "trace_1");
        assertThat(downstream.headers()).containsEntry("x-launchpilot-thread-id", "thread_1");
        assertThat(downstream.headers()).containsEntry("x-launchpilot-workspace-id", "workspace_1");
        assertThat(downstream.headers()).containsEntry("x-launchpilot-campaign-id", "campaign_1");
        assertThat(downstream.headers()).containsKey("traceparent");
        assertThat(downstream.headers().get("traceparent"))
                .matches("^00-[a-f0-9]{32}-[a-f0-9]{16}-01$");
    }

    private CorrelationContext correlation() {
        return new CorrelationContext(
                "req_1",
                "trace_1",
                "thread_1",
                "workspace_1",
                "campaign_1",
                "conversation",
                "handle_command");
    }
}
