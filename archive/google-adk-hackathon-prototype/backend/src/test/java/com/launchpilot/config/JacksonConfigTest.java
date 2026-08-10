package com.launchpilot.config;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.launchpilot.contracts.agent.InternalAgentTurnAcceptedResponse;
import com.launchpilot.contracts.agent.InternalAgentTurnRequest;
import com.launchpilot.contracts.agent.TraceContext;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class JacksonConfigTest {

    private final ObjectMapper mapper = new JacksonConfig().objectMapper();

    @Test
    void serializesContractRecordsAsSnakeCase() throws Exception {
        String json = mapper.writeValueAsString(new InternalAgentTurnRequest(
                "thread_1",
                "workspace_1",
                "campaign_1",
                "hello",
                List.of(Map.of("kind", "csv_import", "id", "imp_1")),
                "2026-06-01T16:30:00+09:00",
                new TraceContext("req_1", "java-backend", "0123456789abcdef0123456789abcdef")));

        assertThat(json).contains("\"thread_id\":\"thread_1\"");
        assertThat(json).contains("\"workspace_id\":\"workspace_1\"");
        assertThat(json).contains("\"campaign_id\":\"campaign_1\"");
        assertThat(json).contains("\"client_created_at\":\"2026-06-01T16:30:00+09:00\"");
        assertThat(json).contains("\"trace_context\":");
        assertThat(json).contains("\"request_id\":\"req_1\"");
        assertThat(json).contains("\"otel_trace_id\":\"0123456789abcdef0123456789abcdef\"");
    }

    @Test
    void deserializesSnakeCaseContractResponses() throws Exception {
        InternalAgentTurnAcceptedResponse response = mapper.readValue("""
                {
                  "ok": true,
                  "thread_id": "thread_1",
                  "accepted_at": "2026-06-01T16:31:00+09:00"
                }
                """, InternalAgentTurnAcceptedResponse.class);

        assertThat(response.ok()).isTrue();
        assertThat(response.threadId()).isEqualTo("thread_1");
        assertThat(response.acceptedAt()).isEqualTo("2026-06-01T16:31:00+09:00");
    }
}
