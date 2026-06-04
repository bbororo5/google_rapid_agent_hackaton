package com.launchpilot.client;

import com.launchpilot.dto.internal.InternalAgentTurnAcceptedResponse;
import com.launchpilot.dto.internal.InternalAgentTurnRequest;
import com.launchpilot.service.ApiException;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/** Python Agent Core(계약 02) 호출. Java는 사용자 turn을 전달하고 스트림을 구독한다. */
@Component
public class AgentServiceClient {

    private final RestClient client;

    /**
     * Creates an AgentServiceClient that uses the provided RestClient to perform HTTP requests to the agent service.
     */
    public AgentServiceClient(RestClient agentRestClient) {
        this.client = agentRestClient;
    }

    public InternalAgentTurnAcceptedResponse sendTurn(InternalAgentTurnRequest request) {
        return client.post()
                .uri("/internal/agent/turns")
                .body(request)
                .retrieve()
                .onStatus(s -> s.value() >= 400, (req, res) -> {
                    throw ApiException.internal("agent turn failed: HTTP " + res.getStatusCode());
                })
                .body(InternalAgentTurnAcceptedResponse.class);
    }
}
