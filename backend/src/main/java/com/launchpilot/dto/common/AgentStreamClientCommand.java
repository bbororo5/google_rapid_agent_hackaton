package com.launchpilot.dto.common;

/** Current FE-facing client command. type is always message.send. */
public record AgentStreamClientCommand(
        String commandId,
        AgentStreamClientCommandType type,
        String threadId,
        String content,
        MessageSendAction action,
        String clientCreatedAt) {}
