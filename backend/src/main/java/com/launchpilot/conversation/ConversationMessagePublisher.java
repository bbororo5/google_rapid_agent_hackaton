package com.launchpilot.conversation;

import com.launchpilot.dto.common.StreamMessage;

/** Publishes committed conversation messages to interested frontend sessions. */
public interface ConversationMessagePublisher {
    void publish(String threadId, StreamMessage message);
}
