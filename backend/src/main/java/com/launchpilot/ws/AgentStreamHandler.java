package com.launchpilot.ws;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.launchpilot.dto.common.AgentStreamClientCommand;
import com.launchpilot.service.AgentStreamRelayService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

/** 계약 01 asyncapi: FE-facing WS 서버 핸들러 (/api/agent/runs/{id}/stream). */
@Component
public class AgentStreamHandler extends TextWebSocketHandler {

    private static final Logger log = LoggerFactory.getLogger(AgentStreamHandler.class);
    private static final String RUN_ID_ATTR = "agentRunId";

    private final AgentStreamSessionRegistry sessions;
    private final AgentStreamRelayService relay;
    private final ObjectMapper mapper;

    public AgentStreamHandler(
            AgentStreamSessionRegistry sessions,
            AgentStreamRelayService relay,
            ObjectMapper mapper) {
        this.sessions = sessions;
        this.relay = relay;
        this.mapper = mapper;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        String runId = extractRunId(session);
        if (runId == null) {
            try {
                session.close(CloseStatus.BAD_DATA);
            } catch (Exception ignored) {
                // closing best-effort
            }
            return;
        }
        session.getAttributes().put(RUN_ID_ATTR, runId);
        sessions.register(runId, session);
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) {
        String runId = (String) session.getAttributes().get(RUN_ID_ATTR);
        if (runId == null) {
            return;
        }
        try {
            AgentStreamClientCommand cmd =
                    mapper.readValue(message.getPayload(), AgentStreamClientCommand.class);
            relay.handleCommand(session, runId, cmd);
        } catch (Exception e) {
            log.warn("client command parse failed (run {}): {}", runId, e.getMessage());
        }
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        String runId = (String) session.getAttributes().get(RUN_ID_ATTR);
        if (runId != null) {
            sessions.unregister(runId, session);
        }
    }

    private String extractRunId(WebSocketSession session) {
        if (session.getUri() == null) {
            return null;
        }
        String path = session.getUri().getPath();
        int start = path.indexOf("/runs/");
        int end = path.lastIndexOf("/stream");
        if (start < 0 || end < 0 || end <= start + 6) {
            return null;
        }
        String runId = path.substring(start + 6, end);
        return runId.matches("^run_[A-Za-z0-9_]+$") ? runId : null;
    }
}
