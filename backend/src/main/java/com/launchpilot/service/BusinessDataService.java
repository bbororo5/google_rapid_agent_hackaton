package com.launchpilot.service;

import com.launchpilot.client.AgentServiceClient;
import com.launchpilot.client.ElasticDocumentWriter;
import com.launchpilot.dto.common.AgentResultPayload;
import com.launchpilot.dto.common.AgentRunStatus;
import com.launchpilot.dto.common.ExperimentItem;
import com.launchpilot.dto.common.Hypothesis;
import com.launchpilot.dto.common.Signal;
import com.launchpilot.dto.elastic.CalendarEventDoc;
import com.launchpilot.dto.elastic.GrowthBriefDoc;
import com.launchpilot.dto.internal.InternalAgentRunStatusResponse;
import com.launchpilot.dto.pub.ApproveExperimentPlanRequest;
import com.launchpilot.dto.pub.ApproveExperimentPlanResponse;
import com.launchpilot.dto.pub.CalendarEventRef;
import java.io.IOException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import org.springframework.stereotype.Service;

/**
 * 인간 승인 -> 불변 산출물 적재 (계약 01 승인 + 계약 03 쓰기).
 * 승인 전에는 어떤 비즈니스 문서도 쓰지 않는다 (MVP-R7).
 */
@Service
public class BusinessDataService {

    private final AgentServiceClient agent;
    private final ElasticDocumentWriter writer;
    private final AgentRunRegistry registry;
    private final IdGenerator ids;

    public BusinessDataService(
            AgentServiceClient agent,
            ElasticDocumentWriter writer,
            AgentRunRegistry registry,
            IdGenerator ids) {
        this.agent = agent;
        this.writer = writer;
        this.registry = registry;
        this.ids = ids;
    }

    public ApproveExperimentPlanResponse approve(
            String agentRunId, ApproveExperimentPlanRequest req) {

        InternalAgentRunStatusResponse run = agent.getRun(agentRunId);

        if (run.status() != AgentRunStatus.WAITING_FOR_APPROVAL) {
            throw new ApiException(409, "CONFLICT",
                    "run is not waiting for approval: " + run.status());
        }
        AgentResultPayload payload = run.payload();
        if (payload == null || payload.experimentPlan() == null) {
            throw new ApiException(409, "CONFLICT", "run has no candidate plan");
        }
        if (!payload.experimentPlan().id().equals(req.experimentPlanId())) {
            throw ApiException.badRequest("experiment_plan_id does not match candidate plan");
        }

        // 1회성 승인: 같은 run으로 이미 적재됐으면 거부 (결정적 brief_id라 재시도는 멱등)
        try {
            if (writer.growthBriefExistsForRun(agentRunId)) {
                throw new ApiException(409, "CONFLICT", "run already approved");
            }
        } catch (IOException e) {
            throw ApiException.internal("approval idempotency check failed: " + e.getMessage());
        }

        AgentRunRegistry.RunContext ctx = registry.get(agentRunId)
                .orElseThrow(() -> ApiException.internal(
                        "missing run context for " + agentRunId));

        String now = OffsetDateTime.now().toString();
        String briefId = ids.briefIdFor(agentRunId);

        List<CalendarEventDoc> events = new ArrayList<>();
        List<CalendarEventRef> eventRefs = new ArrayList<>();
        List<String> eventIds = new ArrayList<>();
        int index = 1;
        for (ExperimentItem exp : req.finalExperiments()) {
            String eventId = ids.calendarEventId(agentRunId, index++);
            events.add(new CalendarEventDoc(
                    eventId,
                    briefId,
                    exp.id(),
                    ctx.workspaceId(),
                    ctx.campaignId(),
                    exp.title(),
                    exp.channel(),
                    exp.scheduledAt(),
                    exp.targetMetric(),
                    exp.successCriteria(),
                    exp.productionBrief(),
                    now));
            eventRefs.add(new CalendarEventRef(eventId, exp.title(), exp.scheduledAt()));
            eventIds.add(eventId);
        }

        GrowthBriefDoc brief = new GrowthBriefDoc(
                briefId,
                ctx.workspaceId(),
                ctx.campaignId(),
                agentRunId,
                req.experimentPlanId(),
                req.approvedBy(),
                now,
                payload.experimentPlan().summary(),
                payload.signals(),
                payload.hypotheses(),
                req.finalExperiments(),
                evidenceRefs(payload),
                eventIds,
                1,
                now);

        try {
            writer.persistApproval(brief, events);
        } catch (IOException e) {
            throw ApiException.internal("approval persistence failed: " + e.getMessage());
        }

        return new ApproveExperimentPlanResponse(
                true,
                "Human approval processed successfully.",
                briefId,
                eventRefs,
                now);
    }

    /** signals + hypotheses의 evidence ref 합집합 (순서 보존, 중복 제거). */
    private List<String> evidenceRefs(AgentResultPayload payload) {
        Set<String> refs = new LinkedHashSet<>();
        if (payload.signals() != null) {
            for (Signal s : payload.signals()) {
                if (s.evidenceRefs() != null) {
                    refs.addAll(s.evidenceRefs());
                }
            }
        }
        if (payload.hypotheses() != null) {
            for (Hypothesis h : payload.hypotheses()) {
                if (h.supportingEvidenceRefs() != null) {
                    refs.addAll(h.supportingEvidenceRefs());
                }
            }
        }
        return new ArrayList<>(refs);
    }
}
