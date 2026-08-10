package com.launchpilot.conversation;

import java.util.Optional;

/** Stores live Java routing context for a conversation thread. */
public interface ThreadContextStore {
    RunContext resolveOrCreate(String threadId);

    void register(String threadId, RunContext context);

    Optional<RunContext> get(String threadId);
}
