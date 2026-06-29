package com.launchpilot.approval;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.launchpilot.conversation.ApprovalGateStore;
import com.launchpilot.conversation.RunContext;
import com.launchpilot.conversation.ThreadContextStore;
import com.launchpilot.contracts.shared.AgentResultPayload;
import com.launchpilot.contracts.shared.ApprovalCommitResult;
import com.launchpilot.contracts.shared.ApprovalGateRequest;
import com.launchpilot.contracts.shared.ExperimentItem;
import com.launchpilot.contracts.shared.Hypothesis;
import com.launchpilot.contracts.shared.Signal;
import com.launchpilot.contracts.elastic.CalendarEventDoc;
import com.launchpilot.contracts.elastic.GrowthBriefDoc;
import com.launchpilot.contracts.frontend.CalendarEventRef;
import com.launchpilot.observability.CorrelationContext;
import com.launchpilot.observability.ObservabilityGateway;
import com.launchpilot.observability.ObservationScope;
import com.launchpilot.observability.ObservedOperation;
import com.launchpilot.observability.OperationKind;
import com.launchpilot.persistence.elastic.ApprovalDocumentRepository;
import com.launchpilot.common.ApiException;
import com.launchpilot.common.IdGenerator;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Service;

/** Deterministic human approval use case. */
@Service
public class ApprovalService implements ApprovalUseCase {

    private static final TypeReference<List<ExperimentItem>> EXPERIMENT_LIST =
            new TypeReference<>() {};

    private final ApprovalGateStore gates;
    private final ThreadContextStore threadContexts;
    private final ApprovalDocumentRepository documents;
    private final IdGenerator ids;
    private final ObjectMapper mapper;
    private final ObservabilityGateway observability;

    public ApprovalService(
            ApprovalGateStore gates,
            ThreadContextStore threadContexts,
            ApprovalDocumentRepository documents,
            IdGenerator ids,
            ObjectMapper mapper,
            ObservabilityGateway observability) {
        this.gates = gates;
        this.threadContexts = threadContexts;
        this.documents = documents;
        this.ids = ids;
        this.mapper = mapper;
        this.observability = observability;
    }

    @Override
    public ApprovalCommitResult approve(ApproveCommand command) {
        CorrelationContext correlation = new CorrelationContext(
                requestId(command),
                requestId(command),
                command.threadId(),
                null,
                null,
                "approval",
                "approve");
        try (ObservationScope scope = observability.startOperation(
                new ObservedOperation("approval.persist", OperationKind.APPROVAL_PERSISTENCE, approvalAttributes(command)),
                correlation)) {
            try {
                ApprovalCommitResult result = approveInternal(command);
                scope.markSuccess(Map.of(
                        "growth_brief_id", result.growthBriefId(),
                        "calendar_event_count", result.createdCalendarEvents().size()));
                return result;
            } catch (RuntimeException e) {
                scope.markFailure(e, approvalAttributes(command));
                throw e;
            }
        }
    }

    private ApprovalCommitResult approveInternal(ApproveCommand command) {
        ApprovalGateRequest gate = gates.get(command.threadId())
                .orElseThrow(() -> new ApiException(409, "CONFLICT", "thread has no candidate plan"));
        if (command.targetId() != null && !command.targetId().equals(gate.approvalId())) {
            throw ApiException.badRequest("approval target mismatch");
        }
        if (command.approvalId() != null && !command.approvalId().equals(gate.approvalId())) {
            throw ApiException.badRequest("approval id mismatch");
        }

        AgentResultPayload payload = gate.payload();
        if (payload == null || payload.experimentPlan() == null) {
            throw new ApiException(409, "CONFLICT", "thread has no candidate plan");
        }
        if (documents.growthBriefExistsForThread(command.threadId())) {
            throw new ApiException(409, "CONFLICT", "thread already approved");
        }

        RunContext ctx = threadContexts.get(command.threadId())
                .orElseThrow(() -> ApiException.internal(
                        "missing thread context for " + command.threadId()));

        String now = OffsetDateTime.now().toString();
        String briefId = ids.briefIdFor(command.threadId());
        List<ExperimentItem> finalExperiments = resolveFinalExperiments(command, gate);

        List<CalendarEventDoc> events = new ArrayList<>();
        List<CalendarEventRef> eventRefs = new ArrayList<>();
        List<String> eventIds = new ArrayList<>();
        int index = 1;
        for (ExperimentItem experiment : finalExperiments) {
            String eventId = ids.calendarEventId(command.threadId(), index++);
            events.add(new CalendarEventDoc(
                    eventId,
                    briefId,
                    experiment.id(),
                    ctx.workspaceId(),
                    ctx.campaignId(),
                    experiment.title(),
                    experiment.channel(),
                    experiment.scheduledAt(),
                    experiment.targetMetric(),
                    experiment.successCriteria(),
                    experiment.productionBrief(),
                    now));
            eventRefs.add(new CalendarEventRef(eventId, experiment.title(), experiment.scheduledAt()));
            eventIds.add(eventId);
        }

        GrowthBriefDoc brief = new GrowthBriefDoc(
                briefId,
                ctx.workspaceId(),
                ctx.campaignId(),
                command.threadId(),
                payload.experimentPlan().id(),
                command.approvedBy(),
                now,
                payload.experimentPlan().summary(),
                payload.signals(),
                payload.hypotheses(),
                finalExperiments,
                evidenceRefs(payload),
                eventIds,
                1,
                now);

        documents.persistApproval(brief, events);
        gates.remove(command.threadId());

        return new ApprovalCommitResult(gate.approvalId(), briefId, eventRefs, now);
    }

    private String requestId(ApproveCommand command) {
        if (command.approvalId() != null && !command.approvalId().isBlank()) {
            return command.approvalId();
        }
        if (command.targetId() != null && !command.targetId().isBlank()) {
            return command.targetId();
        }
        return command.threadId();
    }

    private Map<String, Object> approvalAttributes(ApproveCommand command) {
        Map<String, Object> attributes = new LinkedHashMap<>();
        putIfPresent(attributes, "thread_id", command.threadId());
        putIfPresent(attributes, "approval_id", command.approvalId());
        putIfPresent(attributes, "target_id", command.targetId());
        putIfPresent(attributes, "approved_by", command.approvedBy());
        attributes.put("has_final_experiments", command.actionPayload().containsKey("final_experiments"));
        return attributes;
    }

    private void putIfPresent(Map<String, Object> attributes, String name, Object value) {
        if (value != null) {
            attributes.put(name, value);
        }
    }

    private List<ExperimentItem> resolveFinalExperiments(ApproveCommand command, ApprovalGateRequest gate) {
        Object edited = command.actionPayload().get("final_experiments");
        if (edited != null) {
            return mapper.convertValue(edited, EXPERIMENT_LIST);
        }
        return gate.payload().experimentPlan().items();
    }

    private List<String> evidenceRefs(AgentResultPayload payload) {
        Set<String> refs = new LinkedHashSet<>();
        if (payload.signals() != null) {
            for (Signal signal : payload.signals()) {
                if (signal.evidenceRefs() != null) {
                    refs.addAll(signal.evidenceRefs());
                }
            }
        }
        if (payload.hypotheses() != null) {
            for (Hypothesis hypothesis : payload.hypotheses()) {
                if (hypothesis.supportingEvidenceRefs() != null) {
                    refs.addAll(hypothesis.supportingEvidenceRefs());
                }
            }
        }
        return new ArrayList<>(refs);
    }
}
