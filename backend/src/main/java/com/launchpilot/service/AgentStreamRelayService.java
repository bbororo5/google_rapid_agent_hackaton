package com.launchpilot.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.launchpilot.agentbridge.AgentStreamPort;
import com.launchpilot.agentbridge.AgentTurnCommand;
import com.launchpilot.agentbridge.AgentTurnPort;
import com.launchpilot.conversation.RunContext;
import com.launchpilot.conversation.ThreadContextStore;
import com.launchpilot.dto.common.AgentResultPayload;
import com.launchpilot.dto.common.AgentStreamClientCommand;
import com.launchpilot.dto.common.ApprovalCommitResult;
import com.launchpilot.dto.common.ApprovalGateRequest;
import com.launchpilot.dto.common.ExperimentItem;
import com.launchpilot.dto.common.MessageSendAction;
import com.launchpilot.dto.common.StreamMessage;
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
    private final AgentStreamPort pythonStream;
    private final AgentTurnPort agent;
    private final BusinessDataService business;
    private final ThreadContextStore threads;
    private final IdGenerator ids;
    private final ObjectMapper mapper;

    private final Map<String, ApprovalGateRequest> gates = new ConcurrentHashMap<>();
    private final Set<String> processedCommands = ConcurrentHashMap.newKeySet();
    private final Set<String> startedThreads = ConcurrentHashMap.newKeySet();

    public AgentStreamRelayService(
            AgentThreadTimeline timeline,
            AgentStreamSessionRegistry sessions,
            AgentStreamPort pythonStream,
            AgentTurnPort agent,
            BusinessDataService business,
            ThreadContextStore threads,
            IdGenerator ids,
            ObjectMapper mapper) {
        this.timeline = timeline;
        this.sessions = sessions;
        this.pythonStream = pythonStream;
        this.agent = agent;
        this.business = business;
        this.threads = threads;
        this.ids = ids;
        this.mapper = mapper;
    }

    public void ensureStarted(String threadId) {
        if (startedThreads.add(threadId)) {
            pythonStream.subscribe(threadId, this::onWorkflowEvent);
        }
    }

    /** Replay a thread's committed timeline to a freshly connected session (survives FE refresh). */
    public void replayHistory(String threadId, WebSocketSession session) {
        List<StreamMessage> history = timeline.events(threadId);
        if (history.isEmpty()) {
            return;
        }
        log.info("replay thread={} messages={} -> session {}", threadId, history.size(), session.getId());
        for (StreamMessage message : history) {
            sessions.sendOne(session, message);
        }
        // Re-arm the approval gate so Approve still works after a reconnect.
        if (!gates.containsKey(threadId)) {
            for (StreamMessage message : history) {
                if (message.blocks() != null) {
                    captureApprovalGate(threadId, message.blocks());
                }
            }
        }
    }

    public void handleCommand(WebSocketSession session, String threadId, AgentStreamClientCommand cmd) {
        if (cmd.type() == null || cmd.content() == null || cmd.content().isBlank()) {
            return;
        }
        if (cmd.commandId() != null && !processedCommands.add(cmd.commandId())) {
            return;
        }

        MessageSendAction action = cmd.action();
        log.info("command thread={} action={} content=\"{}\"", threadId,
                action != null ? action.name() : "none", abbreviate(cmd.content().trim()));

        // Always echo the user's message into the public timeline.
        commitAndBroadcast(threadId, "user", List.of(textBlock(cmd.content().trim())));

        // Structured actions are deterministic: Java executes them and they never
        // reach the probabilistic agent. Free-form content goes to the agent core.
        if (action != null && action.name() != null) {
            handleAction(threadId, action, cmd.content().trim());
            return;
        }
        sendTurnToAgentCore(threadId, cmd);
    }

    private static String abbreviate(String s) {
        return s.length() <= 80 ? s : s.substring(0, 80) + "...";
    }

    private void handleAction(String threadId, MessageSendAction action, String content) {
        switch (action.name()) {
            case "approve" -> approve(threadId, action);
            case "reject" -> commitAndBroadcast(threadId, "system",
                    List.of(resultBlock("Approval rejected", content)));
            case "cancel" -> commitAndBroadcast(threadId, "system",
                    List.of(resultBlock("Run cancelled", content)));
            case "revise_artifact" -> {
                // MVP: visual-only edit; the final edited list arrives with approve.final_experiments.
            }
            default -> log.debug("ignoring unknown action {} (thread {})", action.name(), threadId);
        }
    }

    private void sendTurnToAgentCore(String threadId, AgentStreamClientCommand cmd) {
        RunContext ctx = resolveContext(threadId);
        log.info("-> POST /turns thread={} ws={} camp={}", threadId,
                ctx.workspaceId(), ctx.campaignId());
        try {
            agent.submitTurn(new AgentTurnCommand(
                    threadId,
                    ctx.workspaceId(),
                    ctx.campaignId(),
                    cmd.content().trim(),
                    internalAttachments(cmd.attachments()),
                    cmd.clientCreatedAt()));
            log.info("<- /turns accepted thread={}", threadId);
        } catch (Exception e) {
            log.warn("agent turn submit failed (thread {}): {}", threadId, e.getMessage());
        }
    }

    /**
     * Resolve the workspace/campaign context for a thread, registering a live
     * chat thread that import never registered. Falls back to the most recent
     * import's context, then to the configured demo defaults, so the agent
     * always receives a workspace/campaign to scope its evidence queries.
     */
    private RunContext resolveContext(String threadId) {
        return threads.resolveOrCreate(threadId);
    }

    private List<Map<String, Object>> internalAttachments(List<Map<String, Object>> attachments) {
        if (attachments == null || attachments.isEmpty()) {
            return List.of();
        }
        return attachments.stream()
                .filter(attachment -> attachment.get("kind") != null && attachment.get("id") != null)
                .map(attachment -> Map.of(
                        "kind", attachment.get("kind"),
                        "id", attachment.get("id")))
                .toList();
    }

    private void onWorkflowEvent(String threadId, StreamMessage message) {
        List<Map<String, Object>> blocks = message.blocks() == null ? List.of() : message.blocks();
        if (blocks.isEmpty()) {
            return;
        }
        log.info("<- python block thread={} seq={} kinds={}", threadId, message.sequence(),
                blocks.stream().map(b -> String.valueOf(b.get("kind"))).toList());
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

        // Chat threads that reached approval without a prior free-form turn (or
        // after a backend restart that dropped the in-memory registry) won't have
        // a registered context. Lazy-register with the same fallback the turn path
        // uses so approvePayload never throws "missing thread context".
        resolveContext(threadId);

        ApproveExperimentPlanResponse resp;
        try {
            resp = business.approvePayload(threadId, gate.payload(),
                    new ApproveExperimentPlanRequest(
                            gate.payload().experimentPlan().id(),
                            "message.send",
                            resolveFinalExperiments(action, gate)));
        } catch (Exception e) {
            log.error("approve failed (thread {}): {}", threadId, e.getMessage(), e);
            commitAndBroadcast(threadId, "system", List.of(errorBlock(
                    "Approval failed", "Could not persist the experiment plan: " + e.getMessage())));
            return;
        }

        ApprovalCommitResult result = new ApprovalCommitResult(
                gate.approvalId(), resp.growthBriefId(), resp.createdCalendarEvents(), resp.persistedAt());
        commitAndBroadcast(threadId, "assistant", List.of(resultBlock(result)));
        gates.remove(threadId);
    }

    /** Prefer the user's edited final list (revise/select), else the drafted plan items. */
    private List<ExperimentItem> resolveFinalExperiments(MessageSendAction action, ApprovalGateRequest gate) {
        Object edited = action.payload() == null ? null : action.payload().get("final_experiments");
        if (edited != null) {
            return mapper.convertValue(edited, new TypeReference<List<ExperimentItem>>() {});
        }
        return gate.payload().experimentPlan().items();
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
