package com.launchpilot.contracts.shared;

import java.util.Map;

/** Optional structured hint for a UI-originated message.send action. */
public record MessageSendAction(
        String name,
        String targetId,
        Map<String, Object> payload) {}
