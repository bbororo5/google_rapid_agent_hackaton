package com.launchpilot.agentbridge;

import com.launchpilot.dto.internal.InternalAgentTurnAcceptedResponse;

/** Port for submitting a user turn to Python Agent Core. */
public interface AgentTurnPort {
    InternalAgentTurnAcceptedResponse submitTurn(AgentTurnCommand command);
}
