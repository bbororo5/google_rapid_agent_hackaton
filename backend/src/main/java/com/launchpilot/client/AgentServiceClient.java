package com.launchpilot.client;

import com.launchpilot.dto.internal.InternalAgentRunAcceptedResponse;
import com.launchpilot.dto.internal.InternalAgentRunRequest;
import com.launchpilot.dto.internal.InternalAgentRunStatusResponse;
import com.launchpilot.service.ApiException;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/** Python 인프라(계약 02) 호출. Java는 추론하지 않고 트리거/폴링만 한다. */
@Component
public class AgentServiceClient {

    private final RestClient client;

    public AgentServiceClient(RestClient agentRestClient) {
        this.client = agentRestClient;
    }

    public InternalAgentRunAcceptedResponse startRun(InternalAgentRunRequest request) {
        return client.post()
                .uri("/internal/agent/runs")
                .body(request)
                .retrieve()
                .onStatus(s -> s.value() == 409, (req, res) -> {
                    throw new ApiException(409, "RUN_ID_CONFLICT",
                            "agent run already started with a different body");
                })
                .onStatus(s -> s.value() >= 400, (req, res) -> {
                    throw ApiException.internal("agent start failed: HTTP " + res.getStatusCode());
                })
                .body(InternalAgentRunAcceptedResponse.class);
    }

    public InternalAgentRunStatusResponse getRun(String agentRunId) {
        return client.get()
                .uri("/internal/agent/runs/{id}", agentRunId)
                .retrieve()
                .onStatus(s -> s.value() == 404, (req, res) -> {
                    throw ApiException.notFound("agent run not found: " + agentRunId);
                })
                .onStatus(s -> s.value() >= 400, (req, res) -> {
                    throw ApiException.internal("agent poll failed: HTTP " + res.getStatusCode());
                })
                .body(InternalAgentRunStatusResponse.class);
    }
}
