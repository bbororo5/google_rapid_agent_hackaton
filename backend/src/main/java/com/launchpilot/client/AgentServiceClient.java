package com.launchpilot.client;

import com.launchpilot.dto.internal.InternalAgentRunAcceptedResponse;
import com.launchpilot.dto.internal.InternalAgentRunCancelledResponse;
import com.launchpilot.dto.internal.InternalAgentRunRequest;
import com.launchpilot.dto.internal.InternalAgentRunStatusResponse;
import com.launchpilot.service.ApiException;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/** Python 인프라(계약 02) 호출. Java는 추론하지 않고 트리거/폴링만 한다. */
@Component
public class AgentServiceClient {

    private final RestClient client;

    /**
     * Creates an AgentServiceClient that uses the provided RestClient to perform HTTP requests to the agent service.
     */
    public AgentServiceClient(RestClient agentRestClient) {
        this.client = agentRestClient;
    }

    /**
     * Starts an agent run by POSTing the given request to the agent service.
     *
     * @param request the parameters and payload for the agent run
     * @return an InternalAgentRunAcceptedResponse containing details of the accepted run
     * @throws ApiException with status 409 and code "RUN_ID_CONFLICT" if a run with the same ID was already started with a different body
     * @throws ApiException for other HTTP error responses (status >= 400) indicating an internal agent start failure
     */
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

    /**
     * Fetches the current status of an agent run by its identifier.
     *
     * @param agentRunId the identifier of the agent run to retrieve
     * @return the deserialized InternalAgentRunStatusResponse representing the run's current status
     * @throws ApiException if the run is not found (HTTP 404) or if the request fails with any other HTTP status >= 400
     */
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

    /**
     * Cancels an internal agent run via the Python REST fallback endpoint (계약 02).
     *
     * @param agentRunId the identifier of the agent run to cancel
     * @return the deserialized cancellation response from the agent service
     * @throws ApiException if the run is not found (404) or any other HTTP status >= 400
     */
    public InternalAgentRunCancelledResponse cancelRun(String agentRunId) {
        return client.post()
                .uri("/internal/agent/runs/{id}/cancel", agentRunId)
                .retrieve()
                .onStatus(s -> s.value() == 404, (req, res) -> {
                    throw ApiException.notFound("agent run not found: " + agentRunId);
                })
                .onStatus(s -> s.value() >= 400, (req, res) -> {
                    throw ApiException.internal("agent cancel failed: HTTP " + res.getStatusCode());
                })
                .body(InternalAgentRunCancelledResponse.class);
    }
}
