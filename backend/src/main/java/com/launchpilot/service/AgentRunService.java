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

    public AgentRunService(AgentServiceClient agent, AgentRunRegistry registry, IdGenerator ids) {
        this.agent = agent;
        this.registry = registry;
        this.ids = ids;
    }

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

    /** 내부 상태 -> 공개 상태. 내부 전용 필드(agent_diagnostics, *_at) 제거. */
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
