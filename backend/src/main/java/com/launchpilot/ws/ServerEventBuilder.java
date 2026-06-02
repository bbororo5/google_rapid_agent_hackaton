package com.launchpilot.ws;

import com.launchpilot.dto.common.AgentMessage;
import com.launchpilot.dto.common.AgentObservation;
import com.launchpilot.dto.common.AgentResultPayload;
import com.launchpilot.dto.common.AgentRunStatus;
import com.launchpilot.dto.common.AgentStepSnapshot;
import com.launchpilot.dto.common.AgentStreamServerEvent;
import com.launchpilot.dto.common.AgentStreamServerEventType;
import com.launchpilot.dto.common.ApprovalCommitResult;
import com.launchpilot.dto.common.ApprovalGateRequest;
import com.launchpilot.dto.common.ReplayScope;
import com.launchpilot.dto.common.ToolCallLog;

/** AgentStreamServerEvent(18필드 record) 조립용 가변 빌더. 사용 안 한 필드는 null. */
public final class ServerEventBuilder {
    private String eventId;
    private AgentStreamServerEventType type;
    private String agentRunId;
    private String sessionId;
    private Long sequence;
    private String occurredAt;
    private AgentRunStatus status;
    private ReplayScope replayScope;
    private Long lastReplayedSequence;
    private Long nextExpectedSequence;
    private AgentStepSnapshot step;
    private AgentMessage message;
    private AgentObservation observation;
    private ToolCallLog toolCall;
    private AgentResultPayload payload;
    private ApprovalCommitResult approvalResult;
    private ApprovalGateRequest approval;
    private String errorMessage;

    public ServerEventBuilder(AgentStreamServerEventType type) {
        this.type = type;
    }

    public ServerEventBuilder eventId(String v) { this.eventId = v; return this; }
    public ServerEventBuilder agentRunId(String v) { this.agentRunId = v; return this; }
    public ServerEventBuilder sessionId(String v) { this.sessionId = v; return this; }
    public ServerEventBuilder sequence(Long v) { this.sequence = v; return this; }
    public ServerEventBuilder occurredAt(String v) { this.occurredAt = v; return this; }
    public ServerEventBuilder status(AgentRunStatus v) { this.status = v; return this; }
    public ServerEventBuilder replayScope(ReplayScope v) { this.replayScope = v; return this; }
    public ServerEventBuilder lastReplayedSequence(Long v) { this.lastReplayedSequence = v; return this; }
    public ServerEventBuilder nextExpectedSequence(Long v) { this.nextExpectedSequence = v; return this; }
    public ServerEventBuilder step(AgentStepSnapshot v) { this.step = v; return this; }
    public ServerEventBuilder message(AgentMessage v) { this.message = v; return this; }
    public ServerEventBuilder observation(AgentObservation v) { this.observation = v; return this; }
    public ServerEventBuilder toolCall(ToolCallLog v) { this.toolCall = v; return this; }
    public ServerEventBuilder payload(AgentResultPayload v) { this.payload = v; return this; }
    public ServerEventBuilder approvalResult(ApprovalCommitResult v) { this.approvalResult = v; return this; }
    public ServerEventBuilder approval(ApprovalGateRequest v) { this.approval = v; return this; }
    public ServerEventBuilder errorMessage(String v) { this.errorMessage = v; return this; }

    public AgentStreamServerEvent build() {
        return new AgentStreamServerEvent(
                eventId, type, agentRunId, sessionId, sequence, occurredAt, status,
                replayScope, lastReplayedSequence, nextExpectedSequence, step, message,
                observation, toolCall, payload, approvalResult, approval, errorMessage);
    }
}
