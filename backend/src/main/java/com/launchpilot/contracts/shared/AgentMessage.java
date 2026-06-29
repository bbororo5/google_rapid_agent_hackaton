package com.launchpilot.contracts.shared;

/** 계약 01 asyncapi: 대화 타임라인 메시지. role = user | assistant. message_id = msg_*. */
public record AgentMessage(
        String messageId,
        String role,
        String content) {}
