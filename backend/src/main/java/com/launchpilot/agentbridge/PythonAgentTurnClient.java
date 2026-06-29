package com.launchpilot.agentbridge;

import com.launchpilot.dto.internal.InternalAgentTurnAcceptedResponse;
import com.launchpilot.dto.internal.InternalAgentTurnRequest;
import com.launchpilot.service.ApiException;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/** Python Agent Core REST boundary for submitting user turns. */
@Component
public class PythonAgentTurnClient implements AgentTurnPort {

    private final RestClient client;

    public PythonAgentTurnClient(RestClient agentRestClient) {
        this.client = agentRestClient;
    }

    @Override
    public InternalAgentTurnAcceptedResponse submitTurn(AgentTurnCommand command) {
        return client.post()
                .uri("/internal/agent/turns")
                .body(toRequest(command))
                .retrieve()
                .onStatus(s -> s.value() >= 400, (req, res) -> {
                    throw ApiException.internal("agent turn failed: HTTP " + res.getStatusCode());
                })
                .body(InternalAgentTurnAcceptedResponse.class);
    }

    private InternalAgentTurnRequest toRequest(AgentTurnCommand command) {
        return new InternalAgentTurnRequest(
                command.threadId(),
                command.workspaceId(),
                command.campaignId(),
                command.content(),
                command.attachments(),
                command.clientCreatedAt(),
                null);
    }
}
