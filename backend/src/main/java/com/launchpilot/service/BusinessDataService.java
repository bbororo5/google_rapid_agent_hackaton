package com.launchpilot.service;

import com.launchpilot.conversation.RunContext;
import com.launchpilot.conversation.ThreadContextStore;
import com.launchpilot.dto.common.AgentResultPayload;
import com.launchpilot.dto.common.ExperimentItem;
import com.launchpilot.dto.common.Hypothesis;
import com.launchpilot.dto.common.Signal;
import com.launchpilot.dto.elastic.CalendarEventDoc;
import com.launchpilot.dto.elastic.GrowthBriefDoc;
import com.launchpilot.dto.pub.ApproveExperimentPlanRequest;
import com.launchpilot.dto.pub.ApproveExperimentPlanResponse;
import com.launchpilot.dto.pub.CalendarEventRef;
import com.launchpilot.persistence.elastic.ApprovalDocumentRepository;
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

    private final ApprovalDocumentRepository documents;
    private final ThreadContextStore registry;
    private final IdGenerator ids;

    /**
     * Constructs a BusinessDataService with collaborators required to fetch thread status,
     * persist approval artifacts, access run context, and generate stable IDs.
     */
    public BusinessDataService(
            ApprovalDocumentRepository documents,
            ThreadContextStore registry,
            IdGenerator ids) {
        this.documents = documents;
        this.registry = registry;
        this.ids = ids;
    }

    /**
     * Processes a human approval for a specific thread by validating the run and candidate plan,
     * creating calendar event documents and a growth brief, persisting them, and returning identifiers
     * and references for the created artifacts.
     *
     * @param threadId the identifier of the thread to approve
     * @param req the approval request containing the expected experiment plan id, approver, and final experiments
     * @return an ApproveExperimentPlanResponse containing a success flag, a message, the created brief id,
     *         references to created calendar events, and the timestamp of approval
     * @throws ApiException if the run is not waiting for approval, the candidate plan is missing or mismatched,
     *         the run was already approved, or if internal errors occur during idempotency check, context lookup,
     *         or persistence
     */
    public ApproveExperimentPlanResponse approvePayload(
            String threadId, AgentResultPayload payload, ApproveExperimentPlanRequest req) {
        if (payload == null || payload.experimentPlan() == null) {
            throw new ApiException(409, "CONFLICT", "thread has no candidate plan");
        }
        if (!payload.experimentPlan().id().equals(req.experimentPlanId())) {
            throw ApiException.badRequest("experiment_plan_id does not match candidate plan");
        }

        // 1회성 승인: 같은 thread로 이미 적재됐으면 거부 (결정적 brief_id라 재시도는 멱등)
        if (documents.growthBriefExistsForThread(threadId)) {
            throw new ApiException(409, "CONFLICT", "thread already approved");
        }

        RunContext ctx = registry.get(threadId)
                .orElseThrow(() -> ApiException.internal(
                        "missing thread context for " + threadId));

        String now = OffsetDateTime.now().toString();
        String briefId = ids.briefIdFor(threadId);

        List<CalendarEventDoc> events = new ArrayList<>();
        List<CalendarEventRef> eventRefs = new ArrayList<>();
        List<String> eventIds = new ArrayList<>();
        int index = 1;
        for (ExperimentItem exp : req.finalExperiments()) {
            String eventId = ids.calendarEventId(threadId, index++);
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
                threadId,
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

        documents.persistApproval(brief, events);

        return new ApproveExperimentPlanResponse(
                true,
                "Human approval processed successfully.",
                briefId,
                eventRefs,
                now);
    }

    /**
     * Collects evidence reference IDs from the payload's signals and hypotheses, preserving insertion order and removing duplicates.
     *
     * @param payload the thread result payload to extract evidence references from
     * @return a list of unique evidence reference IDs in the order they were first encountered
     */
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
