package com.launchpilot.conversation;

/** Guards idempotency for frontend command ids. */
public interface DuplicateCommandGuard {
    boolean shouldProcess(String commandId);
}
