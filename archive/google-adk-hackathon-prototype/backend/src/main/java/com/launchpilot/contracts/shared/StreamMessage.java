package com.launchpilot.contracts.shared;

import java.util.List;
import java.util.Map;

/** Current FE-facing stream frame: one message with typed UI blocks. */
public record StreamMessage(
        String id,
        String threadId,
        Long sequence,
        String role,
        String createdAt,
        List<Map<String, Object>> blocks) {}
