package com.launchpilot.conversation;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

/** In-memory idempotency guard for frontend command IDs. */
@Component
public class InMemoryDuplicateCommandGuard implements DuplicateCommandGuard {

    private final Set<String> processedCommands = ConcurrentHashMap.newKeySet();

    @Override
    public boolean shouldProcess(String commandId) {
        return commandId == null || processedCommands.add(commandId);
    }
}
