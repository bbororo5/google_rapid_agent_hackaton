package com.launchpilot.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.launchpilot.client.AgentServiceClient;
import com.launchpilot.client.AgentWorkflowStreamClient;
import com.launchpilot.dto.common.AgentResultPayload;
import com.launchpilot.dto.common.AgentStreamClientCommand;
import com.launchpilot.dto.common.ApprovalCommitResult;
import com.launchpilot.dto.common.ApprovalGateRequest;
import com.launchpilot.dto.common.MessageSendAction;
import com.launchpilot.dto.common.StreamMessage;
import com.launchpilot.dto.internal.InternalAgentTurnRequest;
import com.launchpilot.dto.pub.ApproveExperimentPlanRequest;
import com.launchpilot.dto.pub.ApproveExperimentPlanResponse;
import com.launchpilot.ws.AgentThreadTimeline;
import com.launchpilot.ws.AgentStreamSessionRegistry;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.socket.WebSocketSession;

/** Conversation-first FE stream relay. Frontend sees only StreamMessage.blocks[]. */
@Service
public class AgentStreamRelayService {

    private static final Logger log = LoggerFactory.getLogger(AgentStreamRelayService.class);

    private final AgentThreadTimeline timeline;
    private final AgentStreamSessionRegistry sessions;
    private final AgentWorkflowStreamClient pythonStream;
    private final AgentServiceClient agent;
    private final BusinessDataService business;
    private final IdGenerator ids;
    private final ObjectMapper mapper;

    private final Map<String, ApprovalGateRequest> gates = new ConcurrentHashMap<>();
    private final Set<String> processedCommands = ConcurrentHashMap.newKeySet();
    private final Set<String> startedThreads = ConcurrentHashMap.newKeySet();

    public AgentStreamRelayService(
            AgentThreadTimeline timeline,
            AgentStreamSessionRegistry sessions,
            AgentWorkflowStreamClient pythonStream,
            AgentServiceClient agent,
            BusinessDataService business,
            IdGenerator ids,
            ObjectMapper mapper) {
        this.timeline = timeline;
        this.sessions = sessions;
        this.pythonStream = pythonStream;
        this.agent = agent;
        this.business = business;
        this.ids = ids;
        this.mapper = mapper;
    }

    public void ensureStarted(String threadId) {
        if (startedThreads.add(threadId)) {
            pythonStream.connect(threadId, this::onWorkflowEvent);
        }
    }

    public void handleCommand(WebSocketSession session, String threadId, AgentStreamClientCommand cmd) {
        if (cmd.type() == null || cmd.content() == null || cmd.content().isBlank()) {
            return;
        }
        if (cmd.commandId() != null && !processedCommands.add(cmd.commandId())) {
            return;
        }

        commitAndBroadcast(threadId, "user", List.of(textBlock(cmd.content().trim())));
        sendTurnToAgentCore(threadId, cmd);

        MessageSendAction action = cmd.action();
        if (action != null && "approve".equals(action.name())) {
            approve(threadId, action);
        } else if (action != null && ("reject".equals(action.name()) || "cancel".equals(action.name()))) {
            commitAndBroadcast(threadId, "system", List.of(resultBlock(
                    "cancel".equals(action.name()) ? "Run cancelled" : "Approval rejected",
                    cmd.content().trim())));
        }
    }

    private void sendTurnToAgentCore(String threadId, AgentStreamClientCommand cmd) {
        try {
            agent.sendTurn(new InternalAgentTurnRequest(
                    threadId,
                    null,
                    null,
                    cmd.content().trim(),
                    List.of(),
                    cmd.clientCreatedAt(),
                    null));
        } catch (Exception e) {
            log.warn("agent turn submit failed (thread {}): {}", threadId, e.getMessage());
        }
    }

    private void onWorkflowEvent(String threadId, StreamMessage message) {
        List<Map<String, Object>> blocks = message.blocks() == null ? List.of() : message.blocks();
        if (blocks.isEmpty()) {
            return;
        }
        captureApprovalGate(threadId, blocks);
        commitAndBroadcast(threadId, message.role() == null ? "assistant" : message.role(), blocks);
    }

    private void captureApprovalGate(String threadId, List<Map<String, Object>> blocks) {
        if (gates.containsKey(threadId)) {
            return;
        }
        for (Map<String, Object> block : blocks) {
            if (!"approval".equals(block.get("kind")) || block.get("payload") == null) {
                continue;
            }
            AgentResultPayload payload = mapper.convertValue(block.get("payload"), AgentResultPayload.class);
            String approvalId = block.get("id") instanceof String id ? id : ids.newApprovalId();
            gates.put(threadId, new ApprovalGateRequest(
                    approvalId,
                    com.launchpilot.dto.common.ApprovalGateKind.EXPERIMENT_PLAN,
                    payload));
            return;
        }
    }

    private void approve(String threadId, MessageSendAction action) {
        ApprovalGateRequest gate = gates.get(threadId);
        if (gate == null) {
            commitAndBroadcast(threadId, "system", List.of(errorBlock("No approval is open", "There is no approval target for this thread.")));
            return;
        }
        if (action.targetId() != null && !action.targetId().equals(gate.approvalId())) {
            commitAndBroadcast(threadId, "system", List.of(errorBlock("Approval target mismatch", "The requested approval target is no longer active.")));
            return;
        }

        ApproveExperimentPlanResponse resp = business.approvePayload(threadId, gate.payload(),
                new ApproveExperimentPlanRequest(
                        gate.payload().experimentPlan().id(),
                        "message.send",
                        gate.payload().experimentPlan().items()));

        ApprovalCommitResult result = new ApprovalCommitResult(
                gate.approvalId(), resp.growthBriefId(), resp.createdCalendarEvents(), resp.persistedAt());
        commitAndBroadcast(threadId, "assistant", List.of(resultBlock(result)));
        gates.remove(threadId);
    }

    private void commitAndBroadcast(String threadId, String role, List<Map<String, Object>> blocks) {
        var message = timeline.commit(threadId, role, blocks);
        sessions.broadcast(threadId, message);
    }

    private Map<String, Object> textBlock(String text) {
        return Map.of("kind", "text", "text", text);
    }

    private Map<String, Object> resultBlock(ApprovalCommitResult result) {
        return Map.of(
                "kind", "result",
                "title", "Approval complete",
                "detail", "Growth brief " + result.growthBriefId() + " and "
                        + result.createdCalendarEvents().size() + " calendar event(s) are ready.",
                "approval_result", result);
    }

    private Map<String, Object> resultBlock(String title, String detail) {
        return Map.of("kind", "result", "title", title, "detail", detail);
    }

    private Map<String, Object> errorBlock(String title, String detail) {
        return Map.of("kind", "error", "title", title, "detail", detail, "retryable", true);
    }
}
