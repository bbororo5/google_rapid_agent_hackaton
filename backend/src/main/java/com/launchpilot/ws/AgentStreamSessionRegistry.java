package com.launchpilot.ws;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.launchpilot.dto.common.AgentStreamServerEvent;
import java.io.IOException;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;

/** runId -> FE WebSocket 세션 집합. 브로드캐스트 + 단일 세션 송신. */
@Component
public class AgentStreamSessionRegistry {

    private static final Logger log = LoggerFactory.getLogger(AgentStreamSessionRegistry.class);

    private final Map<String, Set<WebSocketSession>> sessions = new ConcurrentHashMap<>();
    private final ObjectMapper mapper;

    public AgentStreamSessionRegistry(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public void register(String agentRunId, WebSocketSession session) {
        sessions.computeIfAbsent(agentRunId, k -> ConcurrentHashMap.newKeySet()).add(session);
    }

    public void unregister(String agentRunId, WebSocketSession session) {
        Set<WebSocketSession> set = sessions.get(agentRunId);
        if (set != null) {
            set.remove(session);
        }
    }

    /** 해당 런을 구독 중인 모든 FE 세션에 이벤트 전송. */
    public void broadcast(String agentRunId, AgentStreamServerEvent event) {
        Set<WebSocketSession> set = sessions.get(agentRunId);
        if (set == null) {
            return;
        }
        String json = serialize(event);
        if (json == null) {
            return;
        }
        for (WebSocketSession s : set) {
            send(s, json);
        }
    }

    /** 단일 세션 전송 (resume 리플레이 등). */
    public void sendTo(WebSocketSession session, AgentStreamServerEvent event) {
        String json = serialize(event);
        if (json != null) {
            send(session, json);
        }
    }

    /** 단일 세션에 임의 메시지(Ack 등) 전송. */
    public void sendObject(WebSocketSession session, Object message) {
        try {
            send(session, mapper.writeValueAsString(message));
        } catch (IOException e) {
            log.warn("ws sendObject failed: {}", e.getMessage());
        }
    }

    private String serialize(AgentStreamServerEvent event) {
        try {
            return mapper.writeValueAsString(event);
        } catch (IOException e) {
            log.warn("server event serialize failed: {}", e.getMessage());
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
