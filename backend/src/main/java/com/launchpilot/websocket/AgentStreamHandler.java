package com.launchpilot.websocket;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.launchpilot.conversation.ClientCommandEnvelope;
import com.launchpilot.conversation.ConversationCommandUseCase;
import com.launchpilot.conversation.ConversationConnectionUseCase;
import com.launchpilot.contracts.shared.AgentStreamClientCommand;
import com.launchpilot.observability.CorrelationContext;
import com.launchpilot.observability.ObservabilityGateway;
import com.launchpilot.observability.ObservedError;
import com.launchpilot.observability.ObservedEvent;
import com.launchpilot.observability.ObservedStatus;
import java.util.LinkedHashMap;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

/** FE-facing conversation WebSocket handler (/api/agent/threads/{threadId}/stream). */
@Component
public class AgentStreamHandler extends TextWebSocketHandler {

    private static final Logger log = LoggerFactory.getLogger(AgentStreamHandler.class);
    private static final String THREAD_ID_ATTR = "threadId";

    private final AgentStreamSessionRegistry sessions;
    private final ConversationConnectionUseCase connections;
    private final ConversationCommandUseCase commands;
    private final ObjectMapper mapper;
    private final ObservabilityGateway observability;

    public AgentStreamHandler(
            AgentStreamSessionRegistry sessions,
            ConversationConnectionUseCase connections,
            ConversationCommandUseCase commands,
            ObjectMapper mapper,
            ObservabilityGateway observability) {
        this.sessions = sessions;
        this.connections = connections;
        this.commands = commands;
        this.mapper = mapper;
        this.observability = observability;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        String threadId = extractThreadId(session);
        if (threadId == null) {
            observability.recordEvent(
                    new ObservedEvent("websocket.session.rejected", ObservedStatus.FAILED, sessionAttributes(session, null)),
                    correlation(null, session.getId(), "open_session"));
            try {
                session.close(CloseStatus.BAD_DATA);
            } catch (Exception ignored) {
                // closing best-effort
            }
            return;
        }
        session.getAttributes().put(THREAD_ID_ATTR, threadId);
        sessions.register(threadId, session);
        observability.recordEvent(
                new ObservedEvent("websocket.session.opened", ObservedStatus.STARTED, sessionAttributes(session, threadId)),
                correlation(threadId, session.getId(), "open_session"));
        connections.openThread(threadId, message -> sessions.sendOne(session, message));
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) {
        String threadId = (String) session.getAttributes().get(THREAD_ID_ATTR);
        if (threadId == null) {
            return;
        }
        try {
            AgentStreamClientCommand cmd =
                    mapper.readValue(message.getPayload(), AgentStreamClientCommand.class);
            if (cmd.type() == null) {
                observability.recordEvent(
                        new ObservedEvent("websocket.message.skipped", ObservedStatus.SKIPPED, sessionAttributes(session, threadId)),
                        correlation(threadId, session.getId(), "handle_message"));
                return;
            }
            commands.handle(new ClientCommandEnvelope(
                    threadId,
                    cmd.commandId(),
                    cmd.content(),
                    cmd.action(),
                    cmd.attachments(),
                    cmd.clientCreatedAt()));
        } catch (Exception e) {
            log.warn("client command parse failed (thread {}): {}", threadId, e.getMessage());
            observability.recordError(
                    new ObservedError("websocket.message.parse_failed", e, sessionAttributes(session, threadId)),
                    correlation(threadId, session.getId(), "handle_message"));
        }
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        String threadId = (String) session.getAttributes().get(THREAD_ID_ATTR);
        if (threadId != null) {
            sessions.unregister(threadId, session);
            Map<String, Object> attributes = sessionAttributes(session, threadId);
            attributes.put("close_code", status.getCode());
            attributes.put("close_reason", status.getReason());
            observability.recordEvent(
                    new ObservedEvent("websocket.session.closed", ObservedStatus.SUCCEEDED, attributes),
                    correlation(threadId, session.getId(), "close_session"));
        }
    }

    private String extractThreadId(WebSocketSession session) {
        if (session.getUri() == null) {
            return null;
        }
        String path = session.getUri().getPath();
        int start = path.indexOf("/threads/");
        int end = path.lastIndexOf("/stream");
        if (start < 0 || end < 0 || end <= start + 9) {
            return null;
        }
        String threadId = path.substring(start + 9, end);
        return threadId.matches("^thread_[A-Za-z0-9_]+$") ? threadId : null;
    }

    private CorrelationContext correlation(String threadId, String requestId, String operation) {
        String resolvedRequestId = requestId == null || requestId.isBlank() ? threadId : requestId;
        return new CorrelationContext(
                resolvedRequestId,
                threadId,
                null,
                null,
                "websocket",
                operation);
    }

    private Map<String, Object> sessionAttributes(WebSocketSession session, String threadId) {
        Map<String, Object> attributes = new LinkedHashMap<>();
        putIfPresent(attributes, "session_id", session.getId());
        putIfPresent(attributes, "thread_id", threadId);
        if (session.getUri() != null) {
            putIfPresent(attributes, "path", session.getUri().getPath());
        }
        return attributes;
    }

    private void putIfPresent(Map<String, Object> attributes, String name, Object value) {
        if (value != null) {
            attributes.put(name, value);
        }
    }
}
