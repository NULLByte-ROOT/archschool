import { useEffect } from "react";
import type { Message } from "../api/client";
import { useChatSocket } from "../hooks/useChatSocket";
import { recordPulseMessage, refreshUnread, setUnreadContext } from "../lib/unread";
import type { ChatSocketEvent } from "../hooks/useChatSocket";
import { useAuth } from "../contexts/AuthContext";

/**
 * One notifications-only connection per session (WebSocket room "pulse").
 *
 * - receives `pulse_ping` frames whenever any message is created anywhere the
 *   user can see (global, own DMs, assignment comment rooms),
 * - resyncs unread counts after every reconnect and every 60s as a safety net
 *   against missed frames.
 *
 * Mounted once in `Layout`, so the Dashboard, Sidebar and Chat list all stay
 * live without any extra sockets when a chat room is open.
 */
export function useUnreadSocket() {
  const { user } = useAuth();
  const userId = user?.id ?? null;

  useEffect(() => {
    setUnreadContext(userId);
    if (userId == null) return;
    void refreshUnread();
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") void refreshUnread();
    }, 60_000);
    return () => {
      window.clearInterval(id);
      setUnreadContext(null);
    };
  }, [userId]);

  useChatSocket(
    "pulse",
    () => {
      // The pulse channel never carries "message" frames.
    },
    (event: ChatSocketEvent) => {
      if (event.type === "pulse_ping" && event.data) {
        recordPulseMessage(event.data as Message);
      }
    },
    {
      onOpen: () => {
        // Frames dropped while disconnected are recovered by the summary call.
        void refreshUnread();
      },
    }
  );
}
