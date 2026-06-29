package com.launchpilot.conversation;

/** Handles one frontend conversation command for a thread. */
public interface ConversationCommandUseCase {
    void handle(ClientCommandEnvelope command);
}
