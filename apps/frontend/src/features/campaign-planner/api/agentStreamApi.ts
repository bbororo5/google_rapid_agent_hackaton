import type { AgentStreamClientCommand, AgentStreamServerEvent } from "@contracts/frontend-types";

export interface AgentStreamConnection {
  send(command: AgentStreamClientCommand): void;
  resume?(): void;
  close(): void;
}

export interface AgentStreamApi {
  connect(input: {
    agentRunId: string;
    streamUrl: string;
    onOpen: () => void;
    onEvent: (event: AgentStreamServerEvent) => void;
    onError: (message: string) => void;
    onClose?: () => void;
    getLastReceivedSequence?: () => number;
  }): AgentStreamConnection;
}

const MAX_RECONNECT_ATTEMPTS = 8;
const MAX_RECONNECT_DELAY_MS = 30000;
const BASE_RECONNECT_DELAY_MS = 1000;

function toWebSocketUrl(streamUrl: string) {
  const url = new URL(streamUrl, window.location.origin);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

function clientId() {
  const storageKey = "launchpilot.agent.client_id";
  const existing = window.localStorage.getItem(storageKey);
  if (existing) return existing;

  const generated = `client_${crypto.randomUUID().replaceAll("-", "_")}`;
  window.localStorage.setItem(storageKey, generated);
  return generated;
}

function commandId(prefix: string) {
  return `${prefix}_${crypto.randomUUID().replaceAll("-", "_")}`;
}

function reconnectDelay(attempt: number) {
  const capped = Math.min(MAX_RECONNECT_DELAY_MS, BASE_RECONNECT_DELAY_MS * 2 ** Math.max(0, attempt - 1));
  return Math.round(capped * (0.7 + Math.random() * 0.6));
}

export function createWebSocketAgentStreamApi(): AgentStreamApi {
  return {
    connect({ agentRunId, streamUrl, onOpen, onEvent, onError, onClose, getLastReceivedSequence }) {
      let socket: WebSocket | null = null;
      let closedByClient = false;
      let reconnectAttempts = 0;
      let reconnectTimer: number | null = null;
      let sessionId: string | null = null;
      const pendingCommands: AgentStreamClientCommand[] = [];
      const wsUrl = toWebSocketUrl(streamUrl);
      const stableClientId = clientId();

      const flushPendingCommands = () => {
        if (!socket || socket.readyState !== WebSocket.OPEN) return;
        while (pendingCommands.length > 0) {
          socket.send(JSON.stringify(pendingCommands.shift()));
        }
      };

      const sendNowOrQueue = (command: AgentStreamClientCommand) => {
        if (socket?.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify(command));
          return;
        }
        pendingCommands.push(command);
      };

      const sendResume = () => {
        sendNowOrQueue({
          command_id: commandId("cmd_resume"),
          type: "connection.resume",
          client_id: stableClientId,
          session_id: sessionId,
          agent_run_id: agentRunId,
          last_received_sequence: getLastReceivedSequence?.() ?? 0,
        });
      };

      const connectSocket = () => {
        socket = new WebSocket(wsUrl);

        socket.addEventListener("open", () => {
          reconnectAttempts = 0;
          onOpen();
          if ((getLastReceivedSequence?.() ?? 0) > 0) {
            sendResume();
          }
          flushPendingCommands();
        });

        socket.addEventListener("message", (message) => {
          try {
            const streamEvent = JSON.parse(message.data as string) as AgentStreamServerEvent;
            if (streamEvent.session_id) {
              sessionId = streamEvent.session_id;
            }
            onEvent(streamEvent);
            if (streamEvent.type === "connection.full_sync_required") {
              sendNowOrQueue({
                command_id: commandId("cmd_full_sync"),
                type: "connection.full_sync",
                client_id: stableClientId,
                session_id: sessionId,
                agent_run_id: agentRunId,
              });
            }
          } catch {
            onError("Agent stream sent an invalid event.");
          }
        });

        socket.addEventListener("error", () => {
          if (socket?.readyState === WebSocket.OPEN) {
            onError("Agent stream connection failed.");
          }
        });

        socket.addEventListener("close", () => {
          onClose?.();
          if (closedByClient) return;
          reconnectAttempts += 1;
          if (reconnectAttempts > MAX_RECONNECT_ATTEMPTS) {
            onError("Agent stream reconnection failed.");
            return;
          }
          reconnectTimer = window.setTimeout(connectSocket, reconnectDelay(reconnectAttempts));
        });
      };

      connectSocket();

      return {
        send(command) {
          sendNowOrQueue(command);
        },
        close() {
          closedByClient = true;
          if (reconnectTimer !== null) {
            window.clearTimeout(reconnectTimer);
          }
          socket?.close();
        },
      };
    },
  };
}
