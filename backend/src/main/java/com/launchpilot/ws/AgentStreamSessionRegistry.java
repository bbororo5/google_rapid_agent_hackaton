package com.launchpilot.ws;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.launchpilot.conversation.ConversationMessagePublisher;
import com.launchpilot.dto.common.StreamMessage;
import java.io.IOException;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;

/** threadId -> FE WebSocket 세션 집합. 브로드캐스트. */
@Component
public class AgentStreamSessionRegistry implements ConversationMessagePublisher {

    private static final Logger log = LoggerFactory.getLogger(AgentStreamSessionRegistry.class);

    private final Map<String, Set<WebSocketSession>> sessions = new ConcurrentHashMap<>();
    private final ObjectMapper mapper;

    public AgentStreamSessionRegistry(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public void register(String threadId, WebSocketSession session) {
        sessions.computeIfAbsent(threadId, k -> ConcurrentHashMap.newKeySet()).add(session);
    }

    public void unregister(String threadId, WebSocketSession session) {
        Set<WebSocketSession> set = sessions.get(threadId);
        if (set != null) {
            set.remove(session);
        }
    }

    @Override
    public void publish(String threadId, StreamMessage message) {
        Set<WebSocketSession> set = sessions.get(threadId);
        if (set == null) {
            return;
        }
        String json = serialize(message);
        if (json == null) {
            return;
        }
        for (WebSocketSession s : set) {
            send(s, json);
        }
    }

    /** Send one message to a single session (used to replay history on connect). */
    public void sendOne(WebSocketSession session, StreamMessage message) {
        String json = serialize(message);
        if (json != null) {
            send(session, json);
        }
    }

    private String serialize(StreamMessage event) {
        try {
            return mapper.writeValueAsString(event);
        } catch (IOException e) {
            log.warn("stream message serialize failed: {}", e.getMessage());
            return null;
        }
    }

    private void send(WebSocketSession session, String json) {
        if (!session.isOpen()) {
            return;
        }
        try {
            // WebSocketSession은 thread-safe하지 않다 -> 세션 단위 동기화.
            synchronized (session) {
                session.sendMessage(new TextMessage(json));
            }
        } catch (IOException e) {
            log.warn("ws send failed (session {}): {}", session.getId(), e.getMessage());
        }
    }
}
