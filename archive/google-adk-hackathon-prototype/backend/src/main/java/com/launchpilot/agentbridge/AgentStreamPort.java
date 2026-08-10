package com.launchpilot.agentbridge;

/** Port for subscribing to Python Agent Core stream messages. */
public interface AgentStreamPort {
    void subscribe(String threadId, AgentStreamListener listener);
}
