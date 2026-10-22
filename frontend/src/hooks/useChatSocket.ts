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
// The backoff is only forgiven once the socket has actually survived this long.
// An "open" that dies instantly (server crash, proxy rejection) must keep the
// exponential backoff, otherwise the client redials once per second forever.
const STABLE_OPEN_MS = 3_000;
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
    // Once the server definitively rejects the session we stop redialling on
    // our own (background events, tab switches) until the user reconnects.
    let stopped = false;
    // "Connecting" must only ever describe the very first load; after the
    // first successful open every later gap is a "reconnecting".
    let hasEverOpened = false;
    let retry = 0;
    let failuresWithoutOpen = 0;
    let openedThisAttempt = false;
    let authCloses = 0;
    let lastAuthCheck = 0;
    let lastFrame = 0;
    let retryTimer: number | undefined;
    let pingTimer: number | undefined;
    let stableTimer: number | undefined;
    let openedAt = 0;

    function hasLiveSocket(): boolean {
      const socket = socketRef.current;
      return (
        socket !== null &&
        (socket.readyState === WebSocket.OPEN ||
          socket.readyState === WebSocket.CONNECTING)
      );
    }

    // Every status transition goes through here, tagged with its trigger, so
    // a misbehaving cycle is immediately visible in the console:
    //   [chat] status open -> reconnecting (close:code=1006 reason=-)
    function setStatusTraced(
      status: ChatSocketStatus,
      trigger: string
    ) {
      setStatus((prev) => {
        if (prev !== status) {
          console.info(`[chat] status ${prev} -> ${status} (${trigger})`);
        }
        return status;
      });
    }

    // Low-frequency contradiction healer: the header may only disagree with
    // the socket for 15s. This guarantees "Online" holds even if some unlisted
    // code path flips the state, and never resurrects a closed socket.
    const reconcilerTimer = window.setInterval(() => {
      if (disposed || paused) return;
      const socket = socketRef.current;
      setStatus((prev) => {
        const live =
          socket !== null && socket.readyState === WebSocket.OPEN;
        if (live && prev !== "open") {
          console.info("[chat] reconciled status -> open (socket was live)");
          return "open";
        }
        return prev;
      });
    }, 15_000);

    function clearTimers() {
      window.clearInterval(pingTimer);
      pingTimer = undefined;
      window.clearTimeout(retryTimer);
      retryTimer = undefined;
      window.clearTimeout(stableTimer);
      stableTimer = undefined;
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
        setStatusTraced("offline", "schedule:navigator.offline");
        return;
      }
      // Never schedule a redial behind a live socket: a stale close event or a
      // slow verifySession() resolving late would otherwise flip the header to
      // "Reconnecting" while the current socket is already healthy — and
      // nothing would ever flip it back (connect() no-ops on live sockets).
      if (hasLiveSocket()) return;
      const exponential = Math.min(BASE_DELAY_MS * 2 ** retry, MAX_DELAY_MS);
      const jittered = Math.round(exponential * (0.8 + Math.random() * 0.4));
      retry += 1;
      setAttempt(retry);
      setStatusTraced("reconnecting", `schedule:retry=${retry}`);
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
      if (disposed || paused || stopped) return;
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
          stopped = true;
          setStatusTraced("auth-failed", "connect:no-token");
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
        hasEverOpened = true;
        openedAt = Date.now();
        stopped = false; // the session works again after a manual retry
        failuresWithoutOpen = 0;
        lastFrame = Date.now();
        setStatusTraced("open", "onopen");
        startHeartbeat(socket);
        onOpenRef.current?.();
        // Forgive the backoff only once the socket has proven it can stay up.
        // Resetting it on a bare "open" let an insta-closing socket (server
        // crash right after accept) redial once per second indefinitely.
        window.clearTimeout(stableTimer);
        stableTimer = window.setTimeout(() => {
          retry = 0;
          setAttempt(0);
        }, STABLE_OPEN_MS);
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
        window.clearTimeout(stableTimer);
        stableTimer = undefined;
        if (socketRef.current === socket) socketRef.current = null;
        if (disposed || paused) return;

        // The requested diagnostic: exactly why the socket went away. `code`
        // 1006 + "(handshake failed)" = TCP/proxy refused; anything else is
        // the peer's close frame. This is info-level on purpose — a failed
        // reconnect cycle logs once per attempt, not once per frame.
        const lifetime = openedAt ? Date.now() - openedAt : 0;
        openedAt = 0;
        console.info(
          "[chat] socket closed code=" + event.code +
            " reason=" + (event.reason || "-") +
            " applied=" + (openedThisAttempt ? "open" : "handshake")
        );
        if (openedThisAttempt && lifetime < STABLE_OPEN_MS) {
          // Nothing the browser can fix: the server accepted the socket and
          // then dropped it within milliseconds (crash after accept, or a
          // proxy killing the upgrade). Point at the place that has the answer.
          console.warn(
            "[chat] socket died " + lifetime +
              "ms after open — closed server-side, check: " +
              "docker logs --tail 100 <backend container>"
          );
        }

        // A stale close from an abandoned/orphan socket must not touch the
        // status: if a different, still-live socket already owns this hook,
        // the drop it belongs to is ancient history.
        if (
          socketRef.current !== null &&
          socketRef.current !== socket &&
          hasLiveSocket()
        ) {
          console.info("[chat] ignore stale close (a newer socket is live)");
          return;
        }

        // Only handshakes that never succeeded count as failures. A drop of an
        // established socket is a network/proxy problem, not a token problem.
        if (!openedThisAttempt) failuresWithoutOpen += 1;
        openedThisAttempt = false;
        setStatusTraced(
          "reconnecting",
          "close:code=" + event.code + " reason=" + (event.reason || "-")
        );

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
          stopped = true;
          setStatusTraced("auth-failed", "close:" + event.code + " x" + authCloses);
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
            stopped = true;
            setStatusTraced("auth-failed", "verify:/auth/me");
            onAuthFailureRef.current?.();
            return;
          }
          // The socket may have been re-established while /auth/me was in
          // flight; scheduleReconnect() itself refuses to run behind a live
          // socket, so this cannot regress the state any more.
          scheduleReconnect();
        });
      };

      socket.onerror = () => {
        // Never call close() here. Closing a socket in the CONNECTING state
        // makes the browser log "WebSocket is closed before the connection is
        // established" — a flood of misleading errors on every failed
        // handshake. The browser fires `onclose` by itself right after the
        // error, and onclose owns all reconnect/backoff logic.
      };
    }

    function handleVisibility() {
      if (document.visibilityState === "hidden") {
        // Do NOT tear the socket down just because the tab went to the
        // background. Browsers keep WebSocket connections alive in background
        // tabs; closing (or aborting a CONNECTING handshake) caused close/
        // redial churn on every alt-tab round trip — and closing during
        // CONNECTING is exactly what floods the console with "WebSocket is
        // closed before the connection is established". `paused` alone just
        // freezes the reconnect scheduling.
        paused = true;
        clearTimers();
        return;
      }

      // Tab is visible again.
      if (disposed || stopped) return;
      paused = false;

      const socket = socketRef.current;
      if (socket && socket.readyState === WebSocket.OPEN) {
        // Returning to a live socket: nudge it instead of redialling, so the
        // header stays "آنلاین" with zero flicker, and the heartbeat watchdog
        // (whose timers were cleared while hidden) starts over with a fresh
        // frame window instead of insta-killling a resumed connection.
        lastFrame = Date.now();
        try {
          socket.send("ping");
        } catch {
          // send() on a dying socket throws; the watchdog/onclose path recovers.
        }
        startHeartbeat(socket);
        return;
      }
      if (socket && socket.readyState === WebSocket.CONNECTING) {
        // A handshake is already in flight; let it finish. Touching it would
        // end up closing a CONNECTING socket.
        return;
      }

      // No usable socket (it died while we were away — paused prevented the
      // close event from scheduling anything). Redial, but keep the honest
      // label: after the first load this is a "reconnecting", not a "connecting".
      retry = 0;
      clearTimers();
      setStatusTraced(
        hasEverOpened ? "reconnecting" : "connecting",
        "visibility:resume"
      );
      connect();
    }

    function handleOnline() {
      if (disposed || paused || stopped) return;
      retry = 0;
      setAttempt(0);
      clearTimers();
      connect();
    }

    reconnectRef.current = () => {
      if (paused) {
        // Resume first so the retry timer can actually fire.
        paused = false;
      }
      if (disposed) return;
      stopped = false;
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
      setStatusTraced(hasEverOpened ? "reconnecting" : "connecting", "reconnect:manual");
      connect();
    };

    connect();
    document.addEventListener("visibilitychange", handleVisibility);
    window.addEventListener("online", handleOnline);

    return () => {
      disposed = true;
      clearTimers();
      window.clearInterval(reconcilerTimer);
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
