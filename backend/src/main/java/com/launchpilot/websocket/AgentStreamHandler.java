package com.launchpilot.websocket;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.launchpilot.conversation.ClientCommandEnvelope;
import com.launchpilot.conversation.ConversationCommandUseCase;
import com.launchpilot.conversation.ConversationConnectionUseCase;
import com.launchpilot.dto.common.AgentStreamClientCommand;
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

    public AgentStreamHandler(
            AgentStreamSessionRegistry sessions,
            ConversationConnectionUseCase connections,
            ConversationCommandUseCase commands,
            ObjectMapper mapper) {
        this.sessions = sessions;
        this.connections = connections;
        this.commands = commands;
        this.mapper = mapper;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        String threadId = extractThreadId(session);
        if (threadId == null) {
            try {
                session.close(CloseStatus.BAD_DATA);
            } catch (Exception ignored) {
                // closing best-effort
            }
            return;
        }
        session.getAttributes().put(THREAD_ID_ATTR, threadId);
        sessions.register(threadId, session);
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
        }
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        String threadId = (String) session.getAttributes().get(THREAD_ID_ATTR);
        if (threadId != null) {
            sessions.unregister(threadId, session);
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
}
