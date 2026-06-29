package com.launchpilot.agentbridge;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class AgentTraceRequestIdsTest {

    @Test
    void keepsExistingReqPrefix() {
        assertThat(AgentTraceRequestIds.normalize("req_20260601_001", "thread_1"))
                .isEqualTo("req_20260601_001");
    }

    @Test
    void prefixesFrontendCommandIdsForAgentContract() {
        assertThat(AgentTraceRequestIds.normalize("cmd_message_123", "thread_1"))
                .isEqualTo("req_cmd_message_123");
    }

    @Test
    void sanitizesUnsupportedCharacters() {
        assertThat(AgentTraceRequestIds.normalize("cmd-message.123", "thread_1"))
                .isEqualTo("req_cmd_message_123");
    }

    @Test
    void fallsBackToThreadIdWhenCommandIdIsMissing() {
        assertThat(AgentTraceRequestIds.normalize(" ", "thread_20260601_001"))
                .isEqualTo("req_thread_20260601_001");
    }
}
