package com.launchpilot.service;

import com.launchpilot.client.AgentServiceClient;
import com.launchpilot.client.AgentWorkflowStreamClient;
import com.launchpilot.dto.common.AgentMessage;
import com.launchpilot.dto.common.AgentResultPayload;
import com.launchpilot.dto.common.AgentRunStatus;
import com.launchpilot.dto.common.AgentStreamAck;
import com.launchpilot.dto.common.AgentStreamClientCommand;
import com.launchpilot.dto.common.AgentStreamServerEvent;
import com.launchpilot.dto.common.AgentStreamServerEventType;
import com.launchpilot.dto.common.ApprovalCommitResult;
import com.launchpilot.dto.common.ApprovalGateKind;
import com.launchpilot.dto.common.ApprovalGateRequest;
import com.launchpilot.dto.common.ReplayScope;
import com.launchpilot.dto.internal.AgentWorkflowEvent;
import com.launchpilot.dto.pub.ApproveExperimentPlanRequest;
import com.launchpilot.dto.pub.ApproveExperimentPlanResponse;
import com.launchpilot.ws.AgentRunTimeline;
import com.launchpilot.ws.AgentStreamSessionRegistry;
import com.launchpilot.ws.ServerEventBuilder;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.socket.WebSocketSession;

/**
 * 계약 01/02 WS 런타임 코어.
 * Python workflow 스트림(02)을 구독해 FE WS 이벤트(01)로 릴레이하고,
 * 승인 게이트/승인 결과/취소/재접속 리플레이를 Java가 소유한다.
 */
@Service
public class AgentStreamRelayService {

    private static final Logger log = LoggerFactory.getLogger(AgentStreamRelayService.class);

    private final AgentRunTimeline timeline;
    private final AgentStreamSessionRegistry sessions;
    private final AgentWorkflowStreamClient pythonStream;
    private final AgentServiceClient agentClient;
    private final BusinessDataService business;
    private final IdGenerator ids;

    /** runId -> 열린 승인 게이트 (approve 검증/적재용). */
    private final Map<String, ApprovalGateRequest> gates = new ConcurrentHashMap<>();
    /** command_id 멱등 (최대 1회 실행). */
    private final Set<String> processedCommands = ConcurrentHashMap.newKeySet();

    public AgentStreamRelayService(
            AgentRunTimeline timeline,
            AgentStreamSessionRegistry sessions,
            AgentWorkflowStreamClient pythonStream,
            AgentServiceClient agentClient,
            BusinessDataService business,
            IdGenerator ids) {
        this.timeline = timeline;
        this.sessions = sessions;
        this.pythonStream = pythonStream;
        this.agentClient = agentClient;
        this.business = business;
        this.ids = ids;
    }

    /** 런 시작: 초기 대화/시작 이벤트 적재 후 Python workflow 스트림 구독. */
    public void startRelay(String agentRunId, String question) {
        if (question != null && !question.isBlank()) {
            AgentMessage msg = new AgentMessage(ids.newMessageId(), "user", question);
            commitAndBroadcast(agentRunId, new ServerEventBuilder(
                    AgentStreamServerEventType.USER_MESSAGE_CREATED).message(msg));
        }
        commitAndBroadcast(agentRunId, new ServerEventBuilder(
                AgentStreamServerEventType.RUN_STARTED).status(AgentRunStatus.PENDING));
        pythonStream.connect(agentRunId, this::onWorkflowEvent);
    }

    /** 02 workflow 이벤트 -> 01 서버 이벤트 릴레이. WAITING_FOR_APPROVAL 도달 시 승인 게이트 합성. */
    private void onWorkflowEvent(String agentRunId, AgentWorkflowEvent w) {
        commitAndBroadcast(agentRunId, new ServerEventBuilder(mapType(w.type()))
                .status(w.status())
                .step(w.step())
                .observation(w.observation())
                .payload(w.payload())
                .errorMessage(w.errorMessage()));

        if (w.status() == AgentRunStatus.WAITING_FOR_APPROVAL
                && w.payload() != null
                && !gates.containsKey(agentRunId)) {
            openApprovalGate(agentRunId, w.payload());
        }
    }

    private void openApprovalGate(String agentRunId, AgentResultPayload payload) {
        ApprovalGateRequest gate = new ApprovalGateRequest(
                ids.newApprovalId(), ApprovalGateKind.EXPERIMENT_PLAN, payload);
        gates.put(agentRunId, gate);
        commitAndBroadcast(agentRunId, new ServerEventBuilder(
                AgentStreamServerEventType.APPROVAL_REQUESTED)
                .status(AgentRunStatus.WAITING_FOR_APPROVAL)
                .approval(gate));
    }

    /** FE 클라 명령 처리 (멱등). */
    public void handleCommand(WebSocketSession session, String agentRunId, AgentStreamClientCommand cmd) {
        if (cmd.type() == null) {
            return;
        }
        switch (cmd.type()) {
            case CONNECTION_RESUME -> replay(session, agentRunId, ReplayScope.MISSED_EVENTS,
                    cmd.lastReceivedSequence() == null ? 0L : cmd.lastReceivedSequence());
            case CONNECTION_FULL_SYNC -> replay(session, agentRunId, ReplayScope.FULL_TIMELINE, 0L);
            case RUN_CANCEL -> { runOnce(cmd, () -> cancel(agentRunId)); ack(session, agentRunId, cmd); }
            case APPROVAL_APPROVE -> { runOnce(cmd, () -> approve(agentRunId, cmd)); ack(session, agentRunId, cmd); }
            case APPROVAL_REJECT, APPROVAL_UPDATE_PAYLOAD -> ack(session, agentRunId, cmd);
            default -> ack(session, agentRunId, cmd);
        }
    }

    private void runOnce(AgentStreamClientCommand cmd, Runnable action) {
        if (cmd.commandId() != null && !processedCommands.add(cmd.commandId())) {
            return; // 이미 실행됨
        }
        action.run();
    }

    private void cancel(String agentRunId) {
        try {
            agentClient.cancelRun(agentRunId);
        } catch (RuntimeException e) {
            log.warn("cancel forward failed (run {}): {}", agentRunId, e.getMessage());
        }
        commitAndBroadcast(agentRunId, new ServerEventBuilder(
                AgentStreamServerEventType.RUN_CANCELLED).status(AgentRunStatus.CANCELLED));
    }

    private void approve(String agentRunId, AgentStreamClientCommand cmd) {
        ApprovalGateRequest gate = gates.get(agentRunId);
        if (gate == null) {
            log.warn("approve with no open gate (run {})", agentRunId);
            return;
        }
        if (cmd.approvalId() != null && !cmd.approvalId().equals(gate.approvalId())) {
            log.warn("approval_id mismatch (run {})", agentRunId);
            return;
        }
        var finalExperiments = (cmd.finalExperiments() != null && !cmd.finalExperiments().isEmpty())
                ? cmd.finalExperiments()
                : gate.payload().experimentPlan().items();
        String approvedBy = cmd.clientId() != null ? cmd.clientId() : "ws-client";

        ApproveExperimentPlanResponse resp = business.approve(agentRunId,
                new ApproveExperimentPlanRequest(
                        gate.payload().experimentPlan().id(), approvedBy, finalExperiments));

        ApprovalCommitResult result = new ApprovalCommitResult(
                gate.approvalId(), resp.growthBriefId(), resp.createdCalendarEvents(), resp.persistedAt());
        commitAndBroadcast(agentRunId, new ServerEventBuilder(
                AgentStreamServerEventType.APPROVAL_COMMITTED)
                .status(AgentRunStatus.SUCCESS)
                .approvalResult(result));
        commitAndBroadcast(agentRunId, new ServerEventBuilder(
                AgentStreamServerEventType.RUN_COMPLETED).status(AgentRunStatus.SUCCESS));
        gates.remove(agentRunId);
    }

    /** 재접속 리플레이: control 이벤트 + 누락 영속 이벤트 재생 (control 이벤트는 미적재). */
    private void replay(WebSocketSession session, String agentRunId, ReplayScope scope, long afterSequence) {
        sessions.sendTo(session, control(agentRunId,
                AgentStreamServerEventType.CONNECTION_RESUME_ACCEPTED).replayScope(scope).build());
        sessions.sendTo(session, control(agentRunId,
                AgentStreamServerEventType.CONNECTION_REPLAY_STARTED).replayScope(scope).build());
        var events = scope == ReplayScope.FULL_TIMELINE
                ? timeline.all(agentRunId)
                : timeline.eventsAfter(agentRunId, afterSequence);
        for (AgentStreamServerEvent e : events) {
            sessions.sendTo(session, e);
        }
        sessions.sendTo(session, control(agentRunId,
                AgentStreamServerEventType.CONNECTION_REPLAY_COMPLETED)
                .lastReplayedSequence(timeline.lastSequence(agentRunId))
                .nextExpectedSequence(timeline.lastSequence(agentRunId) + 1)
                .build());
    }

    private ServerEventBuilder control(String agentRunId, AgentStreamServerEventType type) {
        return new ServerEventBuilder(type)
                .agentRunId(agentRunId)
                .eventId("evt_ctrl_" + System.identityHashCode(this) + "_" + type.name())
                .occurredAt(OffsetDateTime.now().toString());
    }

    private void ack(WebSocketSession session, String agentRunId, AgentStreamClientCommand cmd) {
        sessions.sendObject(session, new AgentStreamAck(
                true, cmd.commandId(), agentRunId, OffsetDateTime.now().toString()));
    }

    private void commitAndBroadcast(String agentRunId, ServerEventBuilder builder) {
        AgentStreamServerEvent event = timeline.commit(agentRunId, builder);
        sessions.broadcast(agentRunId, event);
    }

    private AgentStreamServerEventType mapType(com.launchpilot.dto.internal.AgentWorkflowEventType t) {
        return switch (t) {
            case RUN_STARTED -> AgentStreamServerEventType.RUN_STARTED;
            case STEP_UPDATED -> AgentStreamServerEventType.STEP_UPDATED;
            case OBSERVATION_CREATED -> AgentStreamServerEventType.OBSERVATION_CREATED;
            case SIGNAL_DETECTED -> AgentStreamServerEventType.SIGNAL_DETECTED;
            case HYPOTHESIS_CREATED -> AgentStreamServerEventType.HYPOTHESIS_CREATED;
            case EXPERIMENT_PLAN_DRAFTED -> AgentStreamServerEventType.EXPERIMENT_PLAN_DRAFTED;
            case RUN_CANCELLED -> AgentStreamServerEventType.RUN_CANCELLED;
            case RUN_FAILED -> AgentStreamServerEventType.RUN_FAILED;
        };
    }
}
