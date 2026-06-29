package com.launchpilot.agentbridge;

import com.launchpilot.contracts.agent.InternalAgentTurnAcceptedResponse;
import com.launchpilot.contracts.agent.InternalAgentTurnRequest;
import com.launchpilot.contracts.agent.TraceContext;
import com.launchpilot.common.ApiException;
import com.launchpilot.observability.CorrelationContext;
import com.launchpilot.observability.DownstreamTraceContext;
import com.launchpilot.observability.ObservabilityGateway;
import com.launchpilot.observability.ObservationScope;
import com.launchpilot.observability.ObservedOperation;
import com.launchpilot.observability.OperationKind;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/** Python Agent Core REST boundary for submitting user turns. */
@Component
public class PythonAgentTurnClient implements AgentTurnPort {

    private final RestClient client;
    private final ObservabilityGateway observability;

    public PythonAgentTurnClient(RestClient agentRestClient, ObservabilityGateway observability) {
        this.client = agentRestClient;
        this.observability = observability;
    }

    @Override
    public InternalAgentTurnAcceptedResponse submitTurn(AgentTurnCommand command) {
        CorrelationContext correlation = correlation(command);
        DownstreamTraceContext downstream = observability.downstreamTraceContext(correlation);
        try (ObservationScope scope = observability.startOperation(
                new ObservedOperation("agent.turn.submit", OperationKind.AGENT_TURN_SUBMIT, attributes(command)),
                correlation)) {
            try {
                InternalAgentTurnAcceptedResponse response = client.post()
                        .uri("/internal/agent/turns")
                        .headers(headers -> downstream.headers().forEach(headers::set))
                        .body(toRequest(command, downstream))
                        .retrieve()
                        .onStatus(s -> s.value() >= 400, (req, res) -> {
                            throw ApiException.internal("agent turn failed: HTTP " + res.getStatusCode());
                        })
                        .body(InternalAgentTurnAcceptedResponse.class);
                scope.markSuccess(Map.of("accepted", response != null));
                return response;
            } catch (RuntimeException e) {
                scope.markFailure(e, attributes(command));
                throw e;
            }
        }
    }

    private InternalAgentTurnRequest toRequest(AgentTurnCommand command, DownstreamTraceContext downstream) {
        return new InternalAgentTurnRequest(
                command.threadId(),
                command.workspaceId(),
                command.campaignId(),
                command.content(),
                command.attachments(),
                command.clientCreatedAt(),
                new TraceContext(
                        downstream.requestId(),
                        downstream.source(),
                        downstream.otelTraceId()));
    }

    private CorrelationContext correlation(AgentTurnCommand command) {
        String requestId = requestId(command);
        return new CorrelationContext(
                requestId,
                requestId,
                command.threadId(),
                command.workspaceId(),
                command.campaignId(),
                "agentbridge",
                "submit_turn");
    }

    private Map<String, Object> attributes(AgentTurnCommand command) {
        Map<String, Object> attributes = new LinkedHashMap<>();
        putIfPresent(attributes, "thread_id", command.threadId());
        putIfPresent(attributes, "workspace_id", command.workspaceId());
        putIfPresent(attributes, "campaign_id", command.campaignId());
        putIfPresent(attributes, "command_request_id", command.requestId());
        attributes.put("attachment_count", command.attachments().size());
        return attributes;
    }

    private String requestId(AgentTurnCommand command) {
        return AgentTraceRequestIds.normalize(command.requestId(), command.threadId());
    }

    private void putIfPresent(Map<String, Object> attributes, String name, Object value) {
        if (value != null) {
            attributes.put(name, value);
        }
    }
}
