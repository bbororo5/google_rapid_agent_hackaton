package com.launchpilot.approval;

import com.launchpilot.contracts.shared.AgentResultPayload;
import java.util.Map;

/** Complete deterministic approval commit command. */
public record ApproveCommand(
        String threadId,
        String workspaceId,
        String campaignId,
        String approvalId,
        String targetId,
        AgentResultPayload candidatePayload,
        Map<String, Object> actionPayload,
        String approvedBy) {

    public ApproveCommand {
        actionPayload = actionPayload == null ? Map.of() : Map.copyOf(actionPayload);
    }
}
