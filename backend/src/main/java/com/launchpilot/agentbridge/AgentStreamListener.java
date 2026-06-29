package com.launchpilot.agentbridge;

import com.launchpilot.contracts.shared.StreamMessage;

/** Callback invoked when Python Agent Core emits a stream message. */
public interface AgentStreamListener {
    void onMessage(String threadId, StreamMessage message);
}
