package com.launchpilot.service;

import com.launchpilot.client.AgentServiceClient;
import com.launchpilot.dto.internal.InternalAgentRunRequest;
import com.launchpilot.dto.internal.InternalAgentRunStatusResponse;
import com.launchpilot.dto.internal.TraceContext;
import com.launchpilot.dto.internal.InternalAgentRunCancelledResponse;
import com.launchpilot.dto.pub.AgentRunAcceptedResponse;
import com.launchpilot.dto.pub.AgentRunRequest;
import com.launchpilot.dto.pub.AgentRunStatusResponse;
import com.launchpilot.dto.pub.CancelAgentRunResponse;
import java.time.OffsetDateTime;
import org.springframework.stereotype.Service;

/**
 * 에이전트 런 트리거 + 폴링 중계 (계약 01 <-> 02 번역).
 * Java가 run_id를 생성해 Python에 전달, 생명주기 전체에서 동일 ID 유지.
 * Python의 startRun은 즉시 202 -> 동기 호출로 폴링 일관성 보장.
 */
@Service
public class AgentRunService {

    private final AgentServiceClient agent;
    private final AgentRunRegistry registry;
    private final IdGenerator ids;
    private final AgentStreamRelayService relay;

    /**
     * Create an AgentRunService with its required dependencies.
     *
     * @param agent   client used to start runs and fetch internal run state
     * @param registry registry that stores minimal run context keyed by runId
     * @param ids     generator for run and request identifiers
     * @param relay   WS relay that subscribes the Python workflow stream and pushes FE events
     */
    public AgentRunService(
            AgentServiceClient agent,
            AgentRunRegistry registry,
            IdGenerator ids,
            AgentStreamRelayService relay) {
        this.agent = agent;
        this.registry = registry;
        this.ids = ids;
        this.relay = relay;
    }

    /**
     * Starts an agent run for the given request and returns an acceptance response
     * containing the new runId, location, initial status, and timestamp.
     *
     * @param req the public run request containing workspaceId, campaignId, question,
     *            optional dateRange and parentBriefId
     * @return an AgentRunAcceptedResponse indicating the run was accepted; contains
     *         the generated `runId`, initial status `"PENDING"`, the run location
     *         URI, and a timestamp
     */
    public AgentRunAcceptedResponse runAgent(AgentRunRequest req) {
        String runId = ids.newRunId();
        String requestId = ids.newRequestId();

        registry.put(runId, new AgentRunRegistry.RunContext(req.workspaceId(), req.campaignId()));

        InternalAgentRunRequest internal = new InternalAgentRunRequest(
                runId,
                req.workspaceId(),
                req.campaignId(),
                req.question(),
                req.dateRange(),
                req.parentBriefId(),
                new TraceContext(requestId, "java-backend", null));

        agent.startRun(internal);
        relay.startRelay(runId, req.question());

        return new AgentRunAcceptedResponse(
                true,
                runId,
                "PENDING",
                "/api/agent/runs/" + runId + "/stream",
                "/api/agent/runs/" + runId,
                OffsetDateTime.now().toString());
    }

    /**
     * Cancels an agent run via the Python REST fallback and maps to the public cancel response.
     *
     * @param agentRunId the run to cancel
     * @param reason     optional cancellation reason (currently informational only)
     * @return a CancelAgentRunResponse with status CANCELLED
     */
    public CancelAgentRunResponse cancel(String agentRunId, String reason) {
        InternalAgentRunCancelledResponse i = agent.cancelRun(agentRunId);
        String cancelledAt = i.cancelledAt() != null
                ? i.cancelledAt()
                : OffsetDateTime.now().toString();
        return new CancelAgentRunResponse(true, agentRunId, "CANCELLED", cancelledAt);
    }

    /**
     * Provides the public-facing status for an agent run, omitting internal-only fields.
     *
     * @param agentRunId the identifier of the agent run to poll
     * @return an AgentRunStatusResponse containing the run's public status: `agentRunId`, `status`,
     *         `currentStage`, `retryCount`, `errorMessage`, `payload`, and `toolCallLogs`
     */
    public AgentRunStatusResponse poll(String agentRunId) {
        InternalAgentRunStatusResponse i = agent.getRun(agentRunId);
        return new AgentRunStatusResponse(
                i.agentRunId(),
                i.status(),
                i.currentStage(),
                i.retryCount(),
                i.errorMessage(),
                i.payload(),
                i.toolCallLogs());
    }
}
