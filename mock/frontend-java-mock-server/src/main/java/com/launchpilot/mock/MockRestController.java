package com.launchpilot.mock;

import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class MockRestController {
    private final String publicBaseUrl;

    public MockRestController(@Value("${mock.public-base-url}") String publicBaseUrl) {
        this.publicBaseUrl = publicBaseUrl;
    }

    @GetMapping("/health")
    public Map<String, Object> health() {
        return Map.of("ok", true);
    }

    @PostMapping("/import/csv")
    @ResponseStatus(HttpStatus.CREATED)
    public Map<String, Object> importCsv() {
        return MockPayloads.importCsv();
    }

    @PostMapping("/agent/run")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public Map<String, Object> runAgent() {
        return MockPayloads.acceptedRun(publicBaseUrl);
    }

    @GetMapping("/agent/runs/{agentRunId}")
    public Map<String, Object> getRun(@PathVariable String agentRunId) {
        return MockPayloads.readyRun(agentRunId);
    }

    @PostMapping("/agent/actions/{agentRunId}/approve")
    public Map<String, Object> approve(@RequestBody(required = false) Map<String, Object> request) {
        String title = "BTS face-first hook test";
        if (request != null && request.get("final_experiments") instanceof List<?> experiments && !experiments.isEmpty() && experiments.get(0) instanceof Map<?, ?> first) {
            Object maybeTitle = first.get("title");
            if (maybeTitle instanceof String value && !value.isBlank()) {
                title = value;
            }
        }
        return MockPayloads.approvalResponse(title);
    }

    @PostMapping("/agent/actions/{agentRunId}/cancel")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public Map<String, Object> cancel(@PathVariable String agentRunId) {
        return Map.of(
                "ok", true,
                "agent_run_id", agentRunId,
                "status", "CANCELLED",
                "cancelled_at", "2026-06-01T16:32:30+09:00"
        );
    }
}
