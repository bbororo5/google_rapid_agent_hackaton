package com.launchpilot.conversation;

import com.launchpilot.contracts.shared.StreamMessage;
import java.util.List;
import java.util.Map;

/** Owns thread timeline append and replay semantics. */
public interface ConversationTimeline {
    StreamMessage append(String threadId, String role, List<Map<String, Object>> blocks);

    List<StreamMessage> history(String threadId);
}
