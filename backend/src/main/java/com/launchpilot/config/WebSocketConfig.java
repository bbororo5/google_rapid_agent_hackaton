package com.launchpilot.config;

import com.launchpilot.ws.AgentStreamHandler;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

/** 계약 01 asyncapi: FE-facing WS 엔드포인트 등록. */
@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {

    private final AgentStreamHandler handler;

    public WebSocketConfig(AgentStreamHandler handler) {
        this.handler = handler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(handler, "/api/agent/runs/*/stream")
                .setAllowedOriginPatterns("*");
    }
}
