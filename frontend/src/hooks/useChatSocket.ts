import { useCallback, useEffect, useRef, useState } from "react";
import type { Message } from "../api/client";
import { getWebSocketUrl } from "../api/client";

export function useChatSocket(
  room: string,
  onMessage: (message: Message) => void
) {
  const [connected, setConnected] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);
  const onMessageRef = useRef(onMessage);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    let closed = false;
    let retry = 0;
    let retryTimer: number | undefined;
    let pingTimer: number | undefined;

    function clearPing() {
      if (pingTimer) {
        window.clearInterval(pingTimer);
        pingTimer = undefined;
      }
    }

    function scheduleReconnect() {
      if (closed) return;
      window.clearTimeout(retryTimer);
      const delay = Math.min(1000 * 2 ** retry, 15000);
      retry += 1;
      retryTimer = window.setTimeout(connect, delay);
    }

    function connect() {
      if (closed || document.visibilityState === "hidden") return;
      const existing = socketRef.current;
      if (
        existing &&
        (existing.readyState === WebSocket.OPEN ||
          existing.readyState === WebSocket.CONNECTING)
      ) {
        return;
      }

      const socket = new WebSocket(getWebSocketUrl(room));
      socketRef.current = socket;

      socket.onopen = () => {
        retry = 0;
        setConnected(true);
        clearPing();
        pingTimer = window.setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) socket.send("ping");
        }, 30000);
      };

      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload?.type === "message" && payload.data) {
            onMessageRef.current(payload.data as Message);
          }
        } catch {
          // ignore malformed frames
        }
      };

      socket.onclose = () => {
        clearPing();
        setConnected(false);
        if (socketRef.current === socket) socketRef.current = null;
        scheduleReconnect();
      };

      socket.onerror = () => socket.close();
    }

    function handleVisibility() {
      if (document.visibilityState === "hidden") {
        window.clearTimeout(retryTimer);
        socketRef.current?.close();
      } else {
        retry = 0;
        window.clearTimeout(retryTimer);
        connect();
      }
    }

    connect();
    document.addEventListener("visibilitychange", handleVisibility);

    return () => {
      closed = true;
      window.clearTimeout(retryTimer);
      clearPing();
      document.removeEventListener("visibilitychange", handleVisibility);
      socketRef.current?.close();
      socketRef.current = null;
      setConnected(false);
    };
  }, [room]);

  const send = useCallback((data: Record<string, unknown>) => {
    const socket = socketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(data));
      return true;
    }
    return false;
  }, []);

  return { connected, send };
}
