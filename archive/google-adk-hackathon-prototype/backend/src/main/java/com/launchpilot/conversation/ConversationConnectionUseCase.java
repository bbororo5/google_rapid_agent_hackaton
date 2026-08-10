package com.launchpilot.conversation;

import com.launchpilot.contracts.shared.StreamMessage;
import java.util.function.Consumer;

/** Handles frontend connection lifecycle for a conversation thread. */
public interface ConversationConnectionUseCase {
    void openThread(String threadId, Consumer<StreamMessage> historySink);
}
