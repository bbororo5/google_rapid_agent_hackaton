package com.launchpilot.agentbridge;

import java.util.List;
import java.util.Map;

/** Java-side command for a free-form user turn destined for Python Agent Core. */
public record AgentTurnCommand(
        String threadId,
        String workspaceId,
        String campaignId,
        String content,
        List<Map<String, Object>> attachments,
        String clientCreatedAt,
        String requestId) {

    public AgentTurnCommand {
        attachments = attachments == null ? List.of() : List.copyOf(attachments);
    }
}
