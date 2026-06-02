package com.launchpilot.e2e;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.launchpilot.dto.common.AgentResultPayload;
import com.launchpilot.dto.common.AgentStreamServerEventType;
import com.launchpilot.dto.common.Channel;
import com.launchpilot.dto.common.Confidence;
import com.launchpilot.dto.common.DateRange;
import com.launchpilot.dto.common.ExperimentItem;
import com.launchpilot.dto.common.ExperimentPlan;
import com.launchpilot.dto.common.Hypothesis;
import com.launchpilot.dto.common.Signal;
import com.launchpilot.dto.internal.AgentWorkflowEvent;
import com.launchpilot.dto.internal.AgentWorkflowEventType;
import com.launchpilot.dto.internal.InternalAgentRunAcceptedResponse;
import com.launchpilot.dto.internal.InternalAgentRunCancelledResponse;
import com.launchpilot.ws.AgentRunTimeline;
import java.io.IOException;
import java.net.ServerSocket;
import java.net.URI;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.function.BooleanSupplier;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;
import org.springframework.web.socket.handler.TextWebSocketHandler;

/**
 * 소켓(WS) e2e. 계약 01 asyncapi 스트리밍 경로를 검증한다.
 * 자기-스텁: 앱이 DEFINED_PORT로 뜨고, agent.service.url을 자기 자신으로 가리켜
 *   - REST  /internal/agent/runs              (start, 테스트 스텁 컨트롤러)
 *   - WS    /internal/agent/runs/{id}/stream  (Python workflow 스트림, 테스트 스텁 핸들러)
 * 를 함께 서빙한다. FE는 StandardWebSocketClient로 /api/agent/runs/{id}/stream에 접속.
 * Elastic 미사용 (승인 적재는 검증 범위 밖 -> Elastic e2e는 MainAnalysisApprovalE2ETest).
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.DEFINED_PORT)
@ActiveProfiles("e2e")
@Import(AgentStreamE2ETest.StubConfig.class)
class AgentStreamE2ETest {

    private static final int PORT = freePort();

    @Autowired
    private TestRestTemplate http;

    @Autowired
    private ObjectMapper json;

    @Autowired
    private AgentRunTimeline timeline;

    @DynamicPropertySource
    static void props(DynamicPropertyRegistry registry) {
        registry.add("server.port", () -> PORT);
        registry.add("agent.service.url", () -> "http://localhost:" + PORT);
        // 미사용이지만 Elastic 자동설정 기동을 위한 더미 URI.
        registry.add("spring.elasticsearch.uris", () -> "http://localhost:9200");
    }

    @Test
    void streamsLiveEvents_opensApprovalGate_andReplaysOnFullSync() throws Exception {
        // 1. run_agent -> 202 + stream_url
        ResponseEntity<String> runResp = postJson("/api/agent/run", Map.of(
                "workspace_id", "ws_stream",
                "campaign_id", "camp_stream",
                "question", "What should we test next week?",
                "date_range", Map.of("start", "2026-05-25", "end", "2026-06-01")));
        assertThat(runResp.getStatusCode()).isEqualTo(HttpStatus.ACCEPTED);
        JsonNode runBody = json.readTree(runResp.getBody());
        String runId = runBody.get("agent_run_id").asText();
        assertThat(runId).startsWith("run_");
        assertThat(runBody.get("stream_url").asText())
                .isEqualTo("/api/agent/runs/" + runId + "/stream");

        // 2. 스텁이 push한 워크플로 이벤트가 릴레이되어 승인 게이트가 열릴 때까지 대기 (타임라인 기준).
        await(Duration.ofSeconds(5), () -> timeline.all(runId).stream()
                .anyMatch(e -> e.type() == AgentStreamServerEventType.APPROVAL_REQUESTED));

        // 3. FE WS 접속 후 full_sync 리플레이 요청.
        CollectingHandler fe = new CollectingHandler();
        WebSocketSession feSession = new StandardWebSocketClient()
                .execute(fe, "ws://localhost:" + PORT + "/api/agent/runs/" + runId + "/stream")
                .get(5, TimeUnit.SECONDS);

        send(feSession, Map.of(
                "command_id", "cmd_sync_1",
                "type", "connection.full_sync",
                "client_id", "client_1",
                "agent_run_id", runId));

        // replay_completed 수신까지 대기.
        await(Duration.ofSeconds(5), () -> hasType(fe, "connection.replay_completed"));

        List<JsonNode> events = drain(fe);

        // 영속 타임라인 이벤트 검증.
        assertThat(typesOf(events)).contains(
                "user.message.created", "run.started",
                "experiment_plan.drafted", "approval.requested");

        // approval.requested 는 appr_ 게이트 + payload 포함.
        JsonNode approval = firstOfType(events, "approval.requested");
        assertThat(approval.get("approval").get("approval_id").asText()).startsWith("appr_");
        assertThat(approval.get("approval").get("payload").get("experiment_plan").get("id").asText())
                .startsWith("plan_");

        // sequence 단조 증가 (영속 이벤트만; control 이벤트는 sequence null).
        long prev = 0;
        for (JsonNode e : events) {
            JsonNode seq = e.get("sequence");
            if (seq != null && !seq.isNull()) {
                assertThat(seq.asLong()).isGreaterThan(prev);
                prev = seq.asLong();
            }
        }

        // 4. run.cancel 명령 -> Ack + run.cancelled.
        send(feSession, Map.of(
                "command_id", "cmd_cancel_1",
                "type", "run.cancel",
                "agent_run_id", runId));
        await(Duration.ofSeconds(5), () -> hasAck(fe, "cmd_cancel_1") && hasType(fe, "run.cancelled"));

        feSession.close();
    }

    // ---- helpers ----

    private ResponseEntity<String> postJson(String path, Map<String, ?> body) throws Exception {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        return http.postForEntity(path,
                new HttpEntity<>(json.writeValueAsString(body), headers), String.class);
    }

    private void send(WebSocketSession session, Map<String, ?> command) throws Exception {
        session.sendMessage(new TextMessage(json.writeValueAsString(command)));
    }

    private boolean hasType(CollectingHandler fe, String type) {
        return fe.snapshot().stream().anyMatch(s -> s.contains("\"" + type + "\""));
    }

    private boolean hasAck(CollectingHandler fe, String commandId) {
        return fe.snapshot().stream()
                .anyMatch(s -> s.contains("\"accepted_at\"") && s.contains(commandId));
    }

    private List<JsonNode> drain(CollectingHandler fe) throws IOException {
        List<JsonNode> out = new ArrayList<>();
        for (String s : fe.snapshot()) {
            out.add(json.readTree(s));
        }
        return out;
    }

    private List<String> typesOf(List<JsonNode> events) {
        List<String> out = new ArrayList<>();
        for (JsonNode e : events) {
            if (e.has("type") && e.get("type") != null && !e.get("type").isNull()) {
                out.add(e.get("type").asText());
            }
        }
        return out;
    }

    private JsonNode firstOfType(List<JsonNode> events, String type) {
        return events.stream()
                .filter(e -> e.has("type") && type.equals(e.get("type").asText()))
                .findFirst()
                .orElseThrow(() -> new AssertionError("event not found: " + type));
    }

    private static void await(Duration timeout, BooleanSupplier cond) throws InterruptedException {
        long end = System.currentTimeMillis() + timeout.toMillis();
        while (System.currentTimeMillis() < end) {
            if (cond.getAsBoolean()) {
                return;
            }
            Thread.sleep(50);
        }
        throw new AssertionError("condition not met within " + timeout);
    }

    private static int freePort() {
        try (ServerSocket s = new ServerSocket(0)) {
            return s.getLocalPort();
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
    }

    /** FE WS 수신 메시지 수집. */
    static final class CollectingHandler extends TextWebSocketHandler {
        private final BlockingQueue<String> queue = new LinkedBlockingQueue<>();

        @Override
        protected void handleTextMessage(WebSocketSession session, TextMessage message) {
            queue.add(message.getPayload());
        }

        List<String> snapshot() {
            return new ArrayList<>(queue);
        }
    }

    /** 앱이 자기 자신을 Python으로 스텁: REST start/cancel + WS workflow 스트림. */
    @TestConfiguration
    static class StubConfig {

        @Bean
        StubInternalController stubInternalController() {
            return new StubInternalController();
        }

        @Bean
        PythonStreamStub pythonStreamStub(ObjectMapper mapper) {
            return new PythonStreamStub(mapper);
        }

        @Bean
        WebSocketConfigurer stubWsConfigurer(PythonStreamStub stub) {
            return new WebSocketConfigurer() {
                @Override
                public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
                    registry.addHandler(stub, "/internal/agent/runs/*/stream")
                            .setAllowedOriginPatterns("*");
                }
            };
        }
    }

    /** 계약 02 REST 스텁 (start/cancel). */
    @RestController
    static class StubInternalController {

        @PostMapping("/internal/agent/runs")
        @ResponseStatus(HttpStatus.ACCEPTED)
        InternalAgentRunAcceptedResponse start(@RequestBody Map<String, Object> body) {
            String runId = String.valueOf(body.get("agent_run_id"));
            return new InternalAgentRunAcceptedResponse(
                    true, runId, "PENDING",
                    "/internal/agent/runs/" + runId + "/stream",
                    "/internal/agent/runs/" + runId,
                    OffsetDateTime.now().toString());
        }

        @PostMapping("/internal/agent/runs/{id}/cancel")
        @ResponseStatus(HttpStatus.ACCEPTED)
        InternalAgentRunCancelledResponse cancel(@PathVariable String id) {
            return new InternalAgentRunCancelledResponse(
                    true, id, "CANCELLED", OffsetDateTime.now().toString());
        }
    }

    /** 계약 02 WS 스텁: 접속 시 workflow 이벤트 시퀀스 push (마지막에 WAITING_FOR_APPROVAL + payload). */
    static final class PythonStreamStub extends TextWebSocketHandler {
        private final ObjectMapper mapper;

        PythonStreamStub(ObjectMapper mapper) {
            this.mapper = mapper;
        }

        @Override
        public void afterConnectionEstablished(WebSocketSession session) throws Exception {
            String runId = extractRunId(session);
            int n = 0;
            push(session, event(runId, ++n, AgentWorkflowEventType.RUN_STARTED,
                    "RUNNING_SIGNAL_DETECTION", null));
            push(session, event(runId, ++n, AgentWorkflowEventType.OBSERVATION_CREATED,
                    "RUNNING_EVIDENCE_SEARCH", null));
            push(session, event(runId, ++n, AgentWorkflowEventType.SIGNAL_DETECTED,
                    "RUNNING_EVIDENCE_SEARCH", null));
            push(session, event(runId, ++n, AgentWorkflowEventType.HYPOTHESIS_CREATED,
                    "RUNNING_HYPOTHESIS_GENERATION", null));
            // 마지막: WAITING_FOR_APPROVAL + payload -> relay가 승인 게이트 합성.
            push(session, event(runId, ++n, AgentWorkflowEventType.EXPERIMENT_PLAN_DRAFTED,
                    "WAITING_FOR_APPROVAL", samplePayload()));
        }

        private void push(WebSocketSession session, AgentWorkflowEvent e) throws Exception {
            session.sendMessage(new TextMessage(mapper.writeValueAsString(e)));
        }

        private AgentWorkflowEvent event(
                String runId, int seq, AgentWorkflowEventType type,
                String status, AgentResultPayload payload) {
            return new AgentWorkflowEvent(
                    "wevt_" + seq, type, runId, seq, OffsetDateTime.now().toString(),
                    com.launchpilot.dto.common.AgentRunStatus.valueOf(status),
                    null, null, payload, null);
        }

        private String extractRunId(WebSocketSession session) {
            String path = session.getUri().getPath();
            int start = path.indexOf("/runs/");
            int end = path.lastIndexOf("/stream");
            return path.substring(start + 6, end);
        }

        @Override
        public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
            // no-op
        }
    }

    private static AgentResultPayload samplePayload() {
        Signal signal = new Signal(
                "sig_001", "content_outperformance", "BTS shorts outperformed",
                "desc", "save_rate", 0.074, 0.026, 2.8,
                new DateRange("2026-05-25", "2026-06-01"), Confidence.HIGH,
                List.of("post_014", "post_017"));
        Hypothesis hyp = new Hypothesis(
                "hyp_001", List.of("sig_001"), "Raw BTS clips convert better",
                "rationale", Confidence.MEDIUM_HIGH,
                List.of("post_014"), List.of("correlation, not causal"));
        ExperimentItem item = new ExperimentItem(
                "exp_001", "hyp_001", "BTS face-first hook test", Channel.TIKTOK,
                "12-second short", "close-up hook", "comment CTA",
                "save_rate", "save_rate >= 1.5x baseline in 48h",
                "2026-06-03T20:00:00+09:00", "raw rehearsal footage");
        ExperimentPlan plan = new ExperimentPlan(
                "plan_001", "Test raw BTS across channels", Confidence.MEDIUM_HIGH, List.of(item));
        return new AgentResultPayload(List.of(signal), List.of(hyp), plan);
    }
}
