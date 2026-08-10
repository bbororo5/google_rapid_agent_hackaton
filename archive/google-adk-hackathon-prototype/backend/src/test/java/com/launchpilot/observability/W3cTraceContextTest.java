package com.launchpilot.observability;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class W3cTraceContextTest {

    @Test
    void createsStableW3cTraceContextValues() {
        CorrelationContext correlation = new CorrelationContext(
                "req_1",
                "thread_1",
                "workspace_1",
                "campaign_1",
                "agentbridge",
                "submit_turn");

        String traceId = W3cTraceContext.traceId(correlation);
        String spanId = W3cTraceContext.spanId(correlation);

        assertThat(traceId).matches("^[a-f0-9]{32}$");
        assertThat(spanId).matches("^[a-f0-9]{16}$");
        assertThat(W3cTraceContext.traceId(correlation)).isEqualTo(traceId);
        assertThat(W3cTraceContext.spanId(correlation)).isEqualTo(spanId);
        assertThat(W3cTraceContext.traceparent(traceId, spanId))
                .isEqualTo("00-" + traceId + "-" + spanId + "-01");
    }
}
