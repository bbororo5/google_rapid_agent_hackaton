import type { AgentStreamClientCommand, StreamMessage } from "@contracts/frontend-types";

export interface AgentStreamConnection {
  send(command: AgentStreamClientCommand): void;
  resume?(): void;
  close(): void;
}

export interface AgentStreamApi {
  connect(input: {
    threadId: string;
    streamUrl: string;
    onOpen: () => void;
    onEvent: (message: StreamMessage) => void;
    onError: (message: string) => void;
    onClose?: () => void;
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

function reconnectDelay(attempt: number) {
  const capped = Math.min(MAX_RECONNECT_DELAY_MS, BASE_RECONNECT_DELAY_MS * 2 ** Math.max(0, attempt - 1));
  return Math.round(capped * (0.7 + Math.random() * 0.6));
}

export function createWebSocketAgentStreamApi(): AgentStreamApi {
  return {
    connect({ streamUrl, onOpen, onEvent, onError, onClose }) {
      let socket: WebSocket | null = null;
      let closedByClient = false;
      let reconnectAttempts = 0;
      let reconnectTimer: number | null = null;
      const pendingCommands: AgentStreamClientCommand[] = [];
      const wsUrl = toWebSocketUrl(streamUrl);

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

      const connectSocket = () => {
        socket = new WebSocket(wsUrl);

        socket.addEventListener("open", () => {
          reconnectAttempts = 0;
          onOpen();
          flushPendingCommands();
        });

        socket.addEventListener("message", (message) => {
          try {
            const streamMessage = JSON.parse(message.data as string) as StreamMessage;
            onEvent(streamMessage);
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
