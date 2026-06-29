package com.launchpilot.approval;

import java.util.Map;

/** Transport-neutral approval command from a frontend `message.send` action. */
public record ApproveCommand(
        String threadId,
        String approvalId,
        String targetId,
        Map<String, Object> actionPayload,
        String approvedBy) {

    public ApproveCommand {
        actionPayload = actionPayload == null ? Map.of() : Map.copyOf(actionPayload);
    }
}
