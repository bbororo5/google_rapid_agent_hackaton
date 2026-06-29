package com.launchpilot.conversation;

import com.launchpilot.dto.common.MessageSendAction;
import java.util.List;
import java.util.Map;

/**
 * Transport-neutral representation of a frontend `message.send` command.
 */
public record ClientCommandEnvelope(
        String threadId,
        String commandId,
        String content,
        MessageSendAction action,
        List<Map<String, Object>> attachments,
        String clientCreatedAt) {

    public ClientCommandEnvelope {
        attachments = attachments == null ? List.of() : List.copyOf(attachments);
    }
}
