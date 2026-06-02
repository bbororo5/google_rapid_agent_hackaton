package com.launchpilot.e2e;

import static com.github.tomakehurst.wiremock.client.WireMock.aResponse;
import static com.github.tomakehurst.wiremock.client.WireMock.get;
import static com.github.tomakehurst.wiremock.client.WireMock.post;
import static com.github.tomakehurst.wiremock.client.WireMock.urlEqualTo;
import static com.github.tomakehurst.wiremock.client.WireMock.urlMatching;
import static com.github.tomakehurst.wiremock.stubbing.Scenario.STARTED;
import static org.assertj.core.api.Assertions.assertThat;

import co.elastic.clients.elasticsearch.ElasticsearchClient;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.github.tomakehurst.wiremock.WireMockServer;
import com.github.tomakehurst.wiremock.core.WireMockConfiguration;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;

/**
 * 유일 e2e 테스트. scenarios/main-analysis-approval.scenario.json 흐름을
 * 기동된 Spring 앱에 대해 실행한다.
 * - Python 인프라(계약 02): WireMock 스텁 (계약 02 픽스처).
 * - Elastic(계약 03): 실 Elastic Cloud (영속화 불변 검증).
 * ELASTIC_URL 미설정 시 skip.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("e2e")
@EnabledIfEnvironmentVariable(named = "ELASTIC_URL", matches = ".+")
class MainAnalysisApprovalE2ETest {

    private static final WireMockServer WIREMOCK =
            new WireMockServer(WireMockConfiguration.options().dynamicPort());

    private static final Path CONTRACTS =
            Path.of(System.getProperty("user.dir")).getParent().resolve("contracts");

    @Autowired
    private TestRestTemplate http;

    @Autowired
    private ElasticsearchClient es;

    @Autowired
    private ObjectMapper json;

    // 매 실행 유니크 스코프 -> append-only / 1회성 승인 검사가 재실행 간 깨끗.
    private final String workspaceId = "e2e_ws_" + System.nanoTime();
    private final String campaignId = "e2e_camp_" + System.nanoTime();

    @BeforeAll
    static void startWireMock() throws Exception {
        WIREMOCK.start();
        String startJson = read("02-java-python-agent/examples/start-agent-run-response.json");
        String runningJson = read("02-java-python-agent/examples/get-agent-run-running-response.json");
        String readyJson = read("02-java-python-agent/examples/get-agent-run-ready-response.json");

        WIREMOCK.stubFor(post(urlEqualTo("/internal/agent/runs"))
                .willReturn(jsonResponse(202, startJson)));

        WIREMOCK.stubFor(get(urlMatching("/internal/agent/runs/run_.*"))
                .inScenario("poll").whenScenarioStateIs(STARTED)
                .willReturn(jsonResponse(200, runningJson))
                .willSetStateTo("ready"));

        WIREMOCK.stubFor(get(urlMatching("/internal/agent/runs/run_.*"))
                .inScenario("poll").whenScenarioStateIs("ready")
                .willReturn(jsonResponse(200, readyJson)));
    }

    @AfterAll
    static void stopWireMock() {
        WIREMOCK.stop();
    }

    @DynamicPropertySource
    static void agentServiceUrl(DynamicPropertyRegistry registry) {
        registry.add("agent.service.url", () -> "http://localhost:" + WIREMOCK.port());
    }

    @Test
    void uploadsCsv_runsAgent_approves_andPersistsImmutableArtifacts() throws Exception {
        try {
            // 1. import_csv -> 201
            ResponseEntity<String> importResp = http.postForEntity(
                    "/api/import/csv", csvMultipart(), String.class);
            assertThat(importResp.getStatusCode()).isEqualTo(HttpStatus.CREATED);
            JsonNode importBody = json.readTree(importResp.getBody());
            assertThat(importBody.get("ok").asBoolean()).isTrue();
            assertThat(importBody.get("import_id").asText()).startsWith("imp_");
            assertThat(importBody.get("indexed_count").asInt()).isEqualTo(2);

            // 2. run_agent -> 202 PENDING
            ResponseEntity<String> runResp = postJson("/api/agent/run", Map.of(
                    "workspace_id", workspaceId,
                    "campaign_id", campaignId,
                    "question", "What should we test next week?",
                    "date_range", Map.of("start", "2026-05-25", "end", "2026-06-01")));
            assertThat(runResp.getStatusCode()).isEqualTo(HttpStatus.ACCEPTED);
            JsonNode runBody = json.readTree(runResp.getBody());
            assertThat(runBody.get("status").asText()).isEqualTo("PENDING");
            String agentRunId = runBody.get("agent_run_id").asText();
            assertThat(agentRunId).startsWith("run_");
            assertThat(runBody.get("next_poll_url").asText())
                    .isEqualTo("/api/agent/runs/" + agentRunId);

            // 3. poll_running -> RUNNING_EVIDENCE_SEARCH, payload null
            JsonNode poll1 = json.readTree(
                    http.getForEntity("/api/agent/runs/" + agentRunId, String.class).getBody());
            assertThat(poll1.get("status").asText()).isEqualTo("RUNNING_EVIDENCE_SEARCH");
            assertThat(poll1.get("payload").isNull()).isTrue();

            // 4. poll_ready -> WAITING_FOR_APPROVAL, payload present
            JsonNode poll2 = json.readTree(
                    http.getForEntity("/api/agent/runs/" + agentRunId, String.class).getBody());
            assertThat(poll2.get("status").asText()).isEqualTo("WAITING_FOR_APPROVAL");
            assertThat(poll2.get("payload").isNull()).isFalse();
            // 공개 응답에는 내부 전용 필드가 없어야 한다.
            assertThat(poll2.has("agent_diagnostics")).isFalse();
            assertThat(poll2.has("started_at")).isFalse();

            JsonNode plan = poll2.get("payload").get("experiment_plan");
            String planId = plan.get("id").asText();
            assertThat(planId).startsWith("plan_");

            // 5. approve -> 200, 사용자 편집 제목 보존
            List<Map<String, Object>> finalExperiments =
                    json.convertValue(plan.get("items"), List.class);
            finalExperiments.get(0).put("title", "BTS face-first hook test edited");

            ResponseEntity<String> approveResp = postJson(
                    "/api/agent/actions/" + agentRunId + "/approve", Map.of(
                            "experiment_plan_id", planId,
                            "approved_by", "demo_user",
                            "final_experiments", finalExperiments));
            assertThat(approveResp.getStatusCode()).isEqualTo(HttpStatus.OK);
            JsonNode approveBody = json.readTree(approveResp.getBody());
            assertThat(approveBody.get("ok").asBoolean()).isTrue();
            String briefId = approveBody.get("growth_brief_id").asText();
            assertThat(briefId).startsWith("brief_");
            int expectedEvents = finalExperiments.size();
            assertThat(approveBody.get("created_calendar_events").size()).isEqualTo(expectedEvents);

            // 6. Elastic 영속화 검증
            long briefCount = es.count(c -> c.index("growth_briefs")
                    .query(q -> q.term(t -> t.field("agent_run_id").value(agentRunId)))).count();
            assertThat(briefCount).isEqualTo(1);

            long eventCount = es.count(c -> c.index("calendar_events")
                    .query(q -> q.term(t -> t.field("growth_brief_id").value(briefId)))).count();
            assertThat(eventCount).isEqualTo(expectedEvents);

            // 7. 중복 승인 -> 409 (1회성)
            ResponseEntity<String> dupResp = postJson(
                    "/api/agent/actions/" + agentRunId + "/approve", Map.of(
                            "experiment_plan_id", planId,
                            "approved_by", "demo_user",
                            "final_experiments", finalExperiments));
            assertThat(dupResp.getStatusCode()).isEqualTo(HttpStatus.CONFLICT);
        } finally {
            cleanup();
        }
    }

    private MultiValueMap<String, Object> csvMultipart() {
        ByteArrayResource file = new ByteArrayResource(
                ("post_id,published_at,channel,views,save_rate\n"
                        + "post_014,2026-05-27,tiktok,120000,0.074\n"
                        + "post_017,2026-05-28,tiktok,98000,0.066\n").getBytes()) {
            @Override
            public String getFilename() {
                return "channel_metrics.csv";
            }
        };
        MultiValueMap<String, Object> form = new LinkedMultiValueMap<>();
        form.add("file", file);
        form.add("workspace_id", workspaceId);
        form.add("campaign_id", campaignId);
        return form;
    }

    private ResponseEntity<String> postJson(String path, Map<String, ?> body) throws Exception {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        return http.postForEntity(path,
                new HttpEntity<>(json.writeValueAsString(body), headers), String.class);
    }

    private void cleanup() {
        for (String index : List.of("content_posts", "growth_briefs", "calendar_events")) {
            try {
                es.deleteByQuery(d -> d.index(index).refresh(true)
                        .query(q -> q.term(t -> t.field("workspace_id").value(workspaceId))));
            } catch (Exception ignored) {
                // best-effort teardown
            }
        }
    }

    private static String read(String relative) throws Exception {
        return Files.readString(CONTRACTS.resolve(relative));
    }

    private static com.github.tomakehurst.wiremock.client.ResponseDefinitionBuilder jsonResponse(
            int status, String body) {
        return aResponse()
                .withStatus(status)
                .withHeader("Content-Type", "application/json")
                .withBody(body);
    }
}
