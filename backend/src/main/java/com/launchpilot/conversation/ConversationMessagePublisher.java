package com.launchpilot.conversation;

import com.launchpilot.contracts.shared.StreamMessage;

/** Publishes committed conversation messages to interested frontend sessions. */
public interface ConversationMessagePublisher {
    void publish(String threadId, StreamMessage message);
}
