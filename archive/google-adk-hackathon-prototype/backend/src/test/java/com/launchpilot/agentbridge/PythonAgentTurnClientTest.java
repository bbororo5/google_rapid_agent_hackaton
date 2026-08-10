package com.launchpilot.agentbridge;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.ExpectedCount.once;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.jsonPath;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withAccepted;

import com.launchpilot.observability.LoggingObservabilityGateway;
import com.launchpilot.config.JacksonConfig;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

class PythonAgentTurnClientTest {

    @Test
    void submitsTurnWithTraceHeadersAndContextBody() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("http://agent:8000")
                .messageConverters(converters -> {
                    converters.clear();
                    converters.add(new MappingJackson2HttpMessageConverter(new JacksonConfig().objectMapper()));
                });
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        PythonAgentTurnClient client = new PythonAgentTurnClient(
                builder.build(),
                new LoggingObservabilityGateway());

        server.expect(once(), requestTo("http://agent:8000/internal/agent/turns"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(header("x-launchpilot-request-id", "req_cmd_message_123"))
                .andExpect(header("x-launchpilot-thread-id", "thread_20260601_001"))
                .andExpect(header("x-launchpilot-workspace-id", "workspace_1"))
                .andExpect(header("x-launchpilot-campaign-id", "campaign_1"))
                .andExpect(header("traceparent", org.hamcrest.Matchers.matchesPattern(
                        "^00-[a-f0-9]{32}-[a-f0-9]{16}-01$")))
                .andExpect(jsonPath("$.thread_id").value("thread_20260601_001"))
                .andExpect(jsonPath("$.workspace_id").value("workspace_1"))
                .andExpect(jsonPath("$.campaign_id").value("campaign_1"))
                .andExpect(jsonPath("$.content").value("analyze this"))
                .andExpect(jsonPath("$.trace_context.request_id").value("req_cmd_message_123"))
                .andExpect(jsonPath("$.trace_context.source").value("java-backend"))
                .andExpect(jsonPath("$.trace_context.otel_trace_id", org.hamcrest.Matchers.matchesPattern(
                        "^[a-f0-9]{32}$")))
                .andRespond(withAccepted()
                        .contentType(MediaType.APPLICATION_JSON)
                        .body("""
                                {
                                  "ok": true,
                                  "thread_id": "thread_20260601_001",
                                  "accepted_at": "2026-06-01T16:31:00+09:00"
                                }
                                """));

        var response = client.submitTurn(new AgentTurnCommand(
                "thread_20260601_001",
                "workspace_1",
                "campaign_1",
                "analyze this",
                List.of(Map.of("kind", "csv_import", "id", "imp_1")),
                "2026-06-01T16:30:00+09:00",
                "cmd_message_123"));

        assertThat(response.ok()).isTrue();
        assertThat(response.threadId()).isEqualTo("thread_20260601_001");
        server.verify();
    }
}
