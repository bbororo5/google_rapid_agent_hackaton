package com.launchpilot.client;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.launchpilot.dto.common.StreamMessage;
import java.util.function.BiConsumer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.handler.AbstractWebSocketHandler;

/**
 * 계약 02 asyncapi: Python Agent Core 내부 스트림(WS) 수신 클라이언트.
 * Java는 사용자 turn을 REST로 전달하고 이 스트림을 구독한다.
 */
@Component
public class AgentWorkflowStreamClient {

    private static final Logger log = LoggerFactory.getLogger(AgentWorkflowStreamClient.class);

    private final ObjectMapper mapper;
    private final String wsBaseUrl;
    private final StandardWebSocketClient client = new StandardWebSocketClient();

    public AgentWorkflowStreamClient(
            ObjectMapper mapper,
            @Value("${agent.service.url}") String agentServiceUrl) {
        this.mapper = mapper;
        this.wsBaseUrl = toWs(agentServiceUrl);
    }

    /**
     * Python 내부 스트림에 접속해 workflow 이벤트를 수신하고 onEvent로 넘긴다.
     *
     * @param threadId 구독할 thread id
     * @param onEvent  (threadId, event) 콜백 (relay)
     */
    public void connect(String threadId, BiConsumer<String, StreamMessage> onEvent) {
        String uri = wsBaseUrl + "/internal/agent/threads/" + threadId + "/stream";
        client.execute(new AbstractWebSocketHandler() {
            @Override
            protected void handleTextMessage(WebSocketSession session, TextMessage message) {
                try {
                    StreamMessage e =
                            mapper.readValue(message.getPayload(), StreamMessage.class);
                    onEvent.accept(threadId, e);
                } catch (Exception ex) {
                    log.warn("workflow event parse failed (thread {}): {}", threadId, ex.getMessage());
                }
            }

            @Override
            public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
                log.info("python workflow stream closed (thread {}): {}", threadId, status);
            }
        }, uri).whenComplete((session, ex) -> {
            if (ex != null) {
                log.warn("python workflow stream connect failed (thread {}): {}", threadId, ex.getMessage());
            }
        });
    }

    private static String toWs(String httpUrl) {
        String u = httpUrl.endsWith("/") ? httpUrl.substring(0, httpUrl.length() - 1) : httpUrl;
        if (u.startsWith("https://")) {
            return "wss://" + u.substring("https://".length());
        }
        if (u.startsWith("http://")) {
            return "ws://" + u.substring("http://".length());
        }
        return u;
    }
}
