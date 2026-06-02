package com.launchpilot.service;

import com.launchpilot.client.AgentServiceClient;
import com.launchpilot.dto.internal.InternalAgentRunRequest;
import com.launchpilot.dto.internal.InternalAgentRunStatusResponse;
import com.launchpilot.dto.internal.TraceContext;
import com.launchpilot.dto.pub.AgentRunAcceptedResponse;
import com.launchpilot.dto.pub.AgentRunRequest;
import com.launchpilot.dto.pub.AgentRunStatusResponse;
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

    /**
     * Create an AgentRunService with its required dependencies.
     *
     * @param agent   client used to start runs and fetch internal run state
     * @param registry registry that stores minimal run context keyed by runId
     * @param ids     generator for run and request identifiers
     */
    public AgentRunService(AgentServiceClient agent, AgentRunRegistry registry, IdGenerator ids) {
        this.agent = agent;
        this.registry = registry;
        this.ids = ids;
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

        return new AgentRunAcceptedResponse(
                true,
                runId,
                "PENDING",
                "/api/agent/runs/" + runId,
                OffsetDateTime.now().toString());
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
