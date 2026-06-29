package com.launchpilot.conversation;

import com.launchpilot.agentbridge.AgentStreamPort;
import com.launchpilot.agentbridge.AgentTurnCommand;
import com.launchpilot.agentbridge.AgentTurnPort;
import com.launchpilot.approval.ApprovalUseCase;
import com.launchpilot.approval.ApproveCommand;
import com.launchpilot.contracts.shared.ApprovalCommitResult;
import com.launchpilot.contracts.shared.MessageSendAction;
import com.launchpilot.contracts.shared.StreamMessage;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Consumer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/** Conversation-first frontend stream orchestration. */
@Service
public class ConversationService implements ConversationCommandUseCase, ConversationConnectionUseCase {

    private static final Logger log = LoggerFactory.getLogger(ConversationService.class);

    private final ConversationTimeline timeline;
    private final ConversationMessagePublisher publisher;
    private final AgentStreamPort pythonStream;
    private final AgentTurnPort agent;
    private final ApprovalUseCase approvals;
    private final ApprovalGateStore gates;
    private final ThreadContextStore threads;
    private final DuplicateCommandGuard duplicateCommands;

    private final Set<String> startedThreads = ConcurrentHashMap.newKeySet();

    public ConversationService(
            ConversationTimeline timeline,
            ConversationMessagePublisher publisher,
            AgentStreamPort pythonStream,
            AgentTurnPort agent,
            ApprovalUseCase approvals,
            ApprovalGateStore gates,
            ThreadContextStore threads,
            DuplicateCommandGuard duplicateCommands) {
        this.timeline = timeline;
        this.publisher = publisher;
        this.pythonStream = pythonStream;
        this.agent = agent;
        this.approvals = approvals;
        this.gates = gates;
        this.threads = threads;
        this.duplicateCommands = duplicateCommands;
    }

    @Override
    public void openThread(String threadId, Consumer<StreamMessage> historySink) {
        if (startedThreads.add(threadId)) {
            pythonStream.subscribe(threadId, this::onWorkflowEvent);
        }

        List<StreamMessage> history = timeline.history(threadId);
        if (!history.isEmpty()) {
            log.info("replay thread={} messages={}", threadId, history.size());
            history.forEach(historySink);
        }

        // Re-arm the approval gate so Approve still works after a reconnect.
        if (gates.get(threadId).isEmpty()) {
            for (StreamMessage message : history) {
                if (message.blocks() != null) {
                    gates.captureIfPresent(threadId, message.blocks());
                }
            }
        }
    }

    @Override
    public void handle(ClientCommandEnvelope command) {
        if (command.content() == null || command.content().isBlank()) {
            return;
        }
        if (!duplicateCommands.shouldProcess(command.commandId())) {
            return;
        }

        String content = command.content().trim();
        MessageSendAction action = command.action();
        log.info("command thread={} action={} content=\"{}\"", command.threadId(),
                action != null ? action.name() : "none", abbreviate(content));

        commitAndPublish(command.threadId(), "user", List.of(textBlock(content)));

        // Structured actions are deterministic: Java executes them and they never
        // reach the probabilistic agent. Free-form content goes to the agent core.
        if (action != null && action.name() != null) {
            handleAction(command.threadId(), action, content);
            return;
        }
        sendTurnToAgentCore(command, content);
    }

    private static String abbreviate(String s) {
        return s.length() <= 80 ? s : s.substring(0, 80) + "...";
    }

    private void handleAction(String threadId, MessageSendAction action, String content) {
        switch (action.name()) {
            case "approve" -> approve(threadId, action);
            case "reject" -> commitAndPublish(threadId, "system",
                    List.of(resultBlock("Approval rejected", content)));
            case "cancel" -> commitAndPublish(threadId, "system",
                    List.of(resultBlock("Run cancelled", content)));
            case "revise_artifact" -> {
                // MVP: visual-only edit; the final edited list arrives with approve.final_experiments.
            }
            default -> log.debug("ignoring unknown action {} (thread {})", action.name(), threadId);
        }
    }

    private void sendTurnToAgentCore(ClientCommandEnvelope command, String content) {
        RunContext context = resolveContext(command.threadId());
        log.info("-> POST /turns thread={} ws={} camp={}", command.threadId(),
                context.workspaceId(), context.campaignId());
        try {
            agent.submitTurn(new AgentTurnCommand(
                    command.threadId(),
                    context.workspaceId(),
                    context.campaignId(),
                    content,
                    internalAttachments(command.attachments()),
                    command.clientCreatedAt(),
                    command.commandId()));
            log.info("<- /turns accepted thread={}", command.threadId());
        } catch (Exception e) {
            log.warn("agent turn submit failed (thread {}): {}", command.threadId(), e.getMessage());
        }
    }

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
                blocks.stream().map(block -> String.valueOf(block.get("kind"))).toList());
        gates.captureIfPresent(threadId, blocks);
        commitAndPublish(threadId, message.role() == null ? "assistant" : message.role(), blocks);
    }

    private void approve(String threadId, MessageSendAction action) {
        if (gates.get(threadId).isEmpty()) {
            commitAndPublish(threadId, "system",
                    List.of(errorBlock("No approval is open", "Ask the agent to produce a plan first.")));
            return;
        }
        // Chat threads that reached approval without a prior free-form turn (or
        // after a backend restart that dropped the in-memory registry) won't have
        // a registered context. Lazy-register with the same fallback the turn path
        // uses so approval persistence never misses workspace/campaign context.
        resolveContext(threadId);

        ApprovalCommitResult result;
        try {
            result = approvals.approve(new ApproveCommand(
                    threadId,
                    null,
                    action.targetId(),
                    action.payload(),
                    "message.send"));
        } catch (Exception e) {
            log.error("approve failed (thread {}): {}", threadId, e.getMessage(), e);
            commitAndPublish(threadId, "system", List.of(errorBlock(
                    "Approval failed", "Could not persist the experiment plan: " + e.getMessage())));
            return;
        }

        commitAndPublish(threadId, "assistant", List.of(resultBlock(result)));
    }

    private void commitAndPublish(String threadId, String role, List<Map<String, Object>> blocks) {
        StreamMessage message = timeline.append(threadId, role, blocks);
        publisher.publish(threadId, message);
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
