package com.launchpilot.agentbridge;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.launchpilot.dto.common.StreamMessage;
import jakarta.websocket.ContainerProvider;
import jakarta.websocket.WebSocketContainer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.handler.AbstractWebSocketHandler;

/** Python Agent Core WebSocket boundary for receiving internal stream blocks. */
@Component
public class PythonAgentStreamClient implements AgentStreamPort {

    private static final Logger log = LoggerFactory.getLogger(PythonAgentStreamClient.class);

    // The approval message bundles the whole AgentResultPayload (signals +
    // hypotheses + experiment plan) and runs ~20-40KB. The JSR-356 default text
    // buffer is 8KB, so an oversized frame silently closes the session (1009) and
    // the relay never sees the approval gate. Give the receive buffer generous
    // headroom (4MB) so no single block frame can drop the stream.
    private static final int MAX_TEXT_BUFFER_BYTES = 4 * 1024 * 1024;

    private final ObjectMapper mapper;
    private final String wsBaseUrl;
    private final StandardWebSocketClient client = largeBufferClient();

    public PythonAgentStreamClient(
            ObjectMapper mapper,
            @Value("${agent.service.url}") String agentServiceUrl) {
        this.mapper = mapper;
        this.wsBaseUrl = toWs(agentServiceUrl);
    }

    private static StandardWebSocketClient largeBufferClient() {
        WebSocketContainer container = ContainerProvider.getWebSocketContainer();
        container.setDefaultMaxTextMessageBufferSize(MAX_TEXT_BUFFER_BYTES);
        container.setDefaultMaxBinaryMessageBufferSize(MAX_TEXT_BUFFER_BYTES);
        return new StandardWebSocketClient(container);
    }

    @Override
    public void subscribe(String threadId, AgentStreamListener listener) {
        String uri = wsBaseUrl + "/internal/agent/threads/" + threadId + "/stream";
        client.execute(new AbstractWebSocketHandler() {
            @Override
            protected void handleTextMessage(WebSocketSession session, TextMessage message) {
                try {
                    StreamMessage event =
                            mapper.readValue(message.getPayload(), StreamMessage.class);
                    listener.onMessage(threadId, event);
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
