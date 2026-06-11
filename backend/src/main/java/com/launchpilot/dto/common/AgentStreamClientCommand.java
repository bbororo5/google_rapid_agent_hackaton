package com.launchpilot.dto.common;

import java.util.List;
import java.util.Map;

/** Current FE-facing client command. type is always message.send. */
public record AgentStreamClientCommand(
        String commandId,
        AgentStreamClientCommandType type,
        String threadId,
        String content,
        List<Map<String, Object>> attachments,
        MessageSendAction action,
        String clientCreatedAt) {}
