import { useCallback, useEffect, useRef, useState } from "react";
import type { Message } from "../api/client";
import { fetchMe, getWebSocketUrl } from "../api/client";

export interface ChatSocketEvent {
  type: string;
  data?: unknown;
}

export type ChatSocketStatus =
  | "connecting"
  | "open"
  | "reconnecting"
  | "offline"
  | "auth-failed";

export interface UseChatSocketOptions {
  /** Called after every successful (re)connect, including the first one. */
  onOpen?: () => void;
  /** Called once when the session is definitively rejected. */
  onAuthFailure?: () => void;
}

const BASE_DELAY_MS = 1_000;
const MAX_DELAY_MS = 15_000;
const PING_INTERVAL_MS = 25_000;
// A live socket always answers the ping within a few seconds. Silence for this
// long means the connection was dropped by a proxy without a close frame
// (common right after a blue-green switch), so we must rebuild it ourselves.
const DEAD_SOCKET_MS = 65_000;
const AUTH_CHECK_INTERVAL_MS = 15_000;
// 1008 = policy violation (FastAPI closed before accepting, i.e. bad token).
const AUTH_CLOSE_CODES = new Set([1008, 4001, 4003, 4401, 4403]);

/**
 * Keeps one chat socket alive for `room`.
 *
 * - reconnects with jittered exponential backoff (1s -> 15s),
 * - pauses while the tab is hidden and resumes immediately when it returns,
 * - re-reads the token on every attempt (a login in another tab is picked up),
 * - distinguishes "session is invalid" (log out) from "network/proxy problem"
 *   (keep retrying) by probing `/auth/me` after repeated failures,
 * - pings the server and rebuilds the socket when it goes silent, so a
 *   half-open connection cannot leave the UI stuck on "Connecting…".
 */
export function useChatSocket(
  room: string,
  onMessage: (message: Message) => void,
  onEvent?: (event: ChatSocketEvent) => void,
  options?: UseChatSocketOptions
) {
  const [status, setStatus] = useState<ChatSocketStatus>("connecting");
  const [attempt, setAttempt] = useState(0);
  const socketRef = useRef<WebSocket | null>(null);
  const onMessageRef = useRef(onMessage);
  const onEventRef = useRef(onEvent);
  const onOpenRef = useRef(options?.onOpen);
  const onAuthFailureRef = useRef(options?.onAuthFailure);
  const reconnectRef = useRef<() => void>(() => {});

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    onOpenRef.current = options?.onOpen;
  }, [options?.onOpen]);

  useEffect(() => {
    onAuthFailureRef.current = options?.onAuthFailure;
  }, [options?.onAuthFailure]);

  useEffect(() => {
    let disposed = false;
    let paused = false;
    let retry = 0;
    let failuresWithoutOpen = 0;
    let openedThisAttempt = false;
    let authCloses = 0;
    let lastAuthCheck = 0;
    let lastFrame = 0;
    let retryTimer: number | undefined;
    let pingTimer: number | undefined;

    function clearTimers() {
      window.clearInterval(pingTimer);
      pingTimer = undefined;
      window.clearTimeout(retryTimer);
      retryTimer = undefined;
    }

    function verifySession(): Promise<boolean> {
      const now = Date.now();
      if (now - lastAuthCheck < AUTH_CHECK_INTERVAL_MS) return Promise.resolve(true);
      lastAuthCheck = now;
      return fetchMe()
        .then(() => true)
        .catch((error: unknown) => {
          // `request()` clears the session and redirects to /login on a 401.
          if (error instanceof Error && error.message === "Unauthorized") return false;
          return true; // network hiccup: not an auth problem
        });
    }

    function scheduleReconnect() {
      if (disposed || paused) return;
      if (navigator.onLine === false) {
        setStatus("offline");
        return;
      }
      const exponential = Math.min(BASE_DELAY_MS * 2 ** retry, MAX_DELAY_MS);
      const jittered = Math.round(exponential * (0.8 + Math.random() * 0.4));
      retry += 1;
      setAttempt(retry);
      setStatus("reconnecting");
      window.clearTimeout(retryTimer);
      retryTimer = window.setTimeout(connect, jittered);
    }

    function startHeartbeat(socket: WebSocket) {
      window.clearInterval(pingTimer);
      pingTimer = window.setInterval(() => {
        if (socket.readyState !== WebSocket.OPEN) return;
        if (Date.now() - lastFrame > DEAD_SOCKET_MS) {
          // Half-open socket: close it and rebuild on a clean timeline.
          socket.close(4000, "heartbeat-timeout");
          return;
        }
        socket.send("ping");
      }, PING_INTERVAL_MS);
    }

    function connect() {
      if (disposed || paused) return;
      if (document.visibilityState === "hidden") return;

      const existing = socketRef.current;
      if (
        existing &&
        (existing.readyState === WebSocket.OPEN ||
          existing.readyState === WebSocket.CONNECTING)
      ) {
        return;
      }

      let socket: WebSocket;
      try {
        const url = getWebSocketUrl(room);
        if (!url) {
          // No token in storage: the handshake can only be rejected, so ask the
          // session probe to send the user to /login instead of reconnecting.
          setStatus("auth-failed");
          void fetchMe().catch(() => {
            // 401 already cleared the session and redirected to /login.
          });
          return;
        }
        socket = new WebSocket(url);
      } catch (error) {
        console.error("[chat] could not open the WebSocket", error);
        failuresWithoutOpen += 1;
        scheduleReconnect();
        return;
      }
      socketRef.current = socket;
      openedThisAttempt = false;

      socket.onopen = () => {
        if (disposed) return;
        openedThisAttempt = true;
        retry = 0;
        failuresWithoutOpen = 0;
        lastFrame = Date.now();
        setAttempt(0);
        setStatus("open");
        startHeartbeat(socket);
        onOpenRef.current?.();
      };

      socket.onmessage = (event) => {
        lastFrame = Date.now();
        try {
          const payload = JSON.parse(event.data as string) as ChatSocketEvent;
          if (payload?.type === "message" && payload.data) {
            onMessageRef.current(payload.data as Message);
          } else if (payload?.type && payload.type !== "pong") {
            onEventRef.current?.(payload);
          }
        } catch {
          // ignore malformed frames
        }
      };

      socket.onclose = (event) => {
        window.clearInterval(pingTimer);
        pingTimer = undefined;
        if (socketRef.current === socket) socketRef.current = null;
        if (disposed || paused) return;

        // Only handshakes that never succeeded count as failures. A drop of an
        // established socket is a network/proxy problem, not a token problem.
        if (!openedThisAttempt) failuresWithoutOpen += 1;
        openedThisAttempt = false;
        setStatus("reconnecting");

        if (AUTH_CLOSE_CODES.has(event.code)) {
          authCloses += 1;
        } else {
          authCloses = 0;
        }

        // The server accepted the socket and then refused it with an auth
        // close. If that happens repeatedly while /auth/me still says the
        // session is valid, retrying cannot fix it (a proxy/misconfiguration
        // is refusing this path) — stop hammering and let the REST poll keep
        // the conversation alive.
        if (authCloses >= 3) {
          setStatus("auth-failed");
          onAuthFailureRef.current?.();
          return;
        }

        const authSuspected =
          AUTH_CLOSE_CODES.has(event.code) || failuresWithoutOpen >= 2;
        if (!authSuspected) {
          scheduleReconnect();
          return;
        }

        void verifySession().then((valid) => {
          if (disposed || paused) return;
          if (!valid) {
            setStatus("auth-failed");
            onAuthFailureRef.current?.();
            return;
          }
          scheduleReconnect();
        });
      };

      socket.onerror = () => {
        // `onclose` always follows and owns the reconnect/backoff logic.
        if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
          socket.close();
        }
      };
    }

    function handleVisibility() {
      if (document.visibilityState === "hidden") {
        paused = true;
        clearTimers();
        const socket = socketRef.current;
        socketRef.current = null;
        if (socket) {
          socket.onclose = null;
          socket.onerror = null;
          socket.close(1000, "hidden");
        }
        return;
      }
      paused = false;
      retry = 0;
      setAttempt(0);
      setStatus("connecting");
      clearTimers();
      connect();
    }

    function handleOnline() {
      if (disposed || paused) return;
      retry = 0;
      setAttempt(0);
      clearTimers();
      connect();
    }

    reconnectRef.current = () => {
      if (disposed || paused) return;
      clearTimers();
      const socket = socketRef.current;
      socketRef.current = null;
      if (socket) {
        socket.onclose = null;
        socket.onerror = null;
        socket.close(1000, "manual");
      }
      retry = 0;
      setAttempt(0);
      setStatus("connecting");
      connect();
    };

    connect();
    document.addEventListener("visibilitychange", handleVisibility);
    window.addEventListener("online", handleOnline);

    return () => {
      disposed = true;
      clearTimers();
      document.removeEventListener("visibilitychange", handleVisibility);
      window.removeEventListener("online", handleOnline);
      const socket = socketRef.current;
      socketRef.current = null;
      if (socket) {
        socket.onclose = null;
        socket.onerror = null;
        socket.onmessage = null;
        socket.close(1000, "unmount");
      }
      setStatus("connecting");
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

  const reconnect = useCallback(() => reconnectRef.current(), []);

  return { connected: status === "open", status, attempt, send, reconnect };
}
