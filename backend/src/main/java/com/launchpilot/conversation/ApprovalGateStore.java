package com.launchpilot.conversation;

import com.launchpilot.dto.common.ApprovalGateRequest;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/** Stores the active approval gate captured from Python stream blocks. */
public interface ApprovalGateStore {
    Optional<ApprovalGateRequest> get(String threadId);

    void captureIfPresent(String threadId, List<Map<String, Object>> blocks);

    void remove(String threadId);
}
