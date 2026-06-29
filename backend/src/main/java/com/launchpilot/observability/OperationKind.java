package com.launchpilot.observability;

/**
 * High-level operation category used by observability adapters.
 */
public enum OperationKind {
    HTTP_REQUEST,
    WEBSOCKET_SESSION,
    WEBSOCKET_MESSAGE,
    AGENT_TURN_SUBMIT,
    AGENT_STREAM_RELAY,
    CSV_IMPORT,
    ELASTIC_WRITE,
    ELASTIC_READ,
    APPROVAL_PERSISTENCE
}
