package com.launchpilot.conversation;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.launchpilot.dto.common.AgentResultPayload;
import com.launchpilot.dto.common.ApprovalGateKind;
import com.launchpilot.dto.common.ApprovalGateRequest;
import com.launchpilot.common.IdGenerator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

/** In-memory active approval gate store for the Java conversation runtime. */
@Component
public class InMemoryApprovalGateStore implements ApprovalGateStore {

    private final Map<String, ApprovalGateRequest> gates = new ConcurrentHashMap<>();
    private final ObjectMapper mapper;
    private final IdGenerator ids;

    public InMemoryApprovalGateStore(ObjectMapper mapper, IdGenerator ids) {
        this.mapper = mapper;
        this.ids = ids;
    }

    @Override
    public Optional<ApprovalGateRequest> get(String threadId) {
        return Optional.ofNullable(gates.get(threadId));
    }

    @Override
    public void captureIfPresent(String threadId, List<Map<String, Object>> blocks) {
        if (gates.containsKey(threadId)) {
            return;
        }
        for (Map<String, Object> block : blocks) {
            if (!"approval".equals(block.get("kind")) || block.get("payload") == null) {
                continue;
            }
            AgentResultPayload payload = mapper.convertValue(block.get("payload"), AgentResultPayload.class);
            String approvalId = block.get("id") instanceof String id ? id : ids.newApprovalId();
            gates.put(threadId, new ApprovalGateRequest(
                    approvalId,
                    ApprovalGateKind.EXPERIMENT_PLAN,
                    payload));
            return;
        }
    }

    @Override
    public void remove(String threadId) {
        gates.remove(threadId);
    }
}
