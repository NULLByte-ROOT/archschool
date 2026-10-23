import { useSyncExternalStore } from "react";
import {
  fetchUnreadSummary,
  markRoomRead as apiMarkRoomRead,
} from "../api/client";
import type { Message } from "../api/client";
import { messagePreview } from "./chat";

/**
 * Unread counts + a live activity feed ("Pulse"), shared by the Sidebar, the
 * Chat list and the Dashboard — an external store fed from three places:
 *
 * - `refreshUnread()`      → GET /messages/unread (on login, socket open, 60s)
 * - `recordPulseMessage()` → real-time `pulse_ping` frames on the pulse socket
 * - `markRoomRead()`       → optimistic zero + POST /messages/{room}/read
 */

export interface PulseItem {
  id: number;
  room: string;
  /** "chat" = global/DM message, "comment" = assignment comment */
  kind: "chat" | "comment";
  sender: string | null;
  avatar: string | null;
  preview: string;
  createdAt: string;
  assignmentId: number | null;
  assignmentTitle: string | null;
}

export interface UnreadState {
  counts: Record<string, number>;
  total: number;
  feed: PulseItem[];
}

let state: UnreadState = { counts: {}, total: 0, feed: [] };
const listeners = new Set<() => void>();
let activeRoom: string | null = null;
let currentUserId: number | null = null;
let refreshing = false;
const recentReadCalls = new Map<string, number>();

function emit() {
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot(): UnreadState {
  return state;
}

function countTotal(counts: Record<string, number>): number {
  let total = 0;
  for (const value of Object.values(counts)) total += value;
  return total;
}

/** The room key a message belongs to (matches the backend WS room strings). */
export function roomOfMessage(message: Message): string {
  if (message.assignment_id != null) {
    return `assignment:${message.assignment_id}`;
  }
  if (message.receiver_id != null) {
    const low = Math.min(message.sender_id, message.receiver_id);
    const high = Math.max(message.sender_id, message.receiver_id);
    return `dm:${low}:${high}`;
  }
  return "global";
}

export function toPulseItem(message: Message): PulseItem {
  return {
    id: message.id,
    room: roomOfMessage(message),
    kind: message.assignment_id != null ? "comment" : "chat",
    sender: message.sender_username ?? null,
    avatar: message.sender_avatar_url ?? null,
    preview: messagePreview(message),
    createdAt: message.created_at,
    assignmentId: message.assignment_id ?? null,
    assignmentTitle: message.assignment_title ?? null,
  };
}

/** Who is currently keeping a room open (its badge must never inflate). */
export function setActiveRoom(room: string | null) {
  activeRoom = room;
}

export function setUnreadContext(userId: number | null) {
  currentUserId = userId;
}

export function resetUnread() {
  activeRoom = null;
  currentUserId = null;
  recentReadCalls.clear();
  state = { counts: {}, total: 0, feed: [] };
  emit();
}

function incrementRoom(room: string) {
  const counts = { ...state.counts };
  counts[room] = (counts[room] ?? 0) + 1;
  state = { ...state, counts, total: countTotal(counts) };
  emit();
}

/** A message just landed (pulse socket). Feed always updates; the count only
 * grows when the room is not the one the user is actively looking at. */
export function recordPulseMessage(message: Message) {
  const room = roomOfMessage(message);
  const item = toPulseItem(message);

  const feed = state.feed.some((entry) => entry.id === item.id)
    ? state.feed
    : [item, ...state.feed].slice(0, 16);

  state = { ...state, feed };
  if (room !== activeRoom) incrementRoom(room);
  emit();
}

/** Merge initial data (overview + recent comments) into the feed. */
export function seedFeed(items: PulseItem[]) {
  if (items.length === 0) return;
  const seen = new Set<number>();
  const merged = [...items, ...state.feed]
    .filter((item) => {
      if (seen.has(item.id)) return false;
      seen.add(item.id);
      return true;
    })
    .sort(
      (a, b) =>
        new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
    )
    .slice(0, 16);
  state = { ...state, feed: merged };
  emit();
}

/** Optimistic zero + fire-and-forget POST. Throttled per room. */
export function markRoomRead(room: string) {
  if (!room || currentUserId == null) return;
  const now = Date.now();
  const last = recentReadCalls.get(room) ?? 0;
  if (now - last < 2_000) return;
  recentReadCalls.set(room, now);

  if ((state.counts[room] ?? 0) > 0) {
    const counts = { ...state.counts };
    delete counts[room];
    state = { ...state, counts, total: countTotal(counts) };
    emit();
  }
  void apiMarkRoomRead(room).catch(() => {
    // A failed POST keeps the badge; the next refresh reconciles it.
  });
}

/** Authoritative resync from the server. */
export function refreshUnread() {
  if (currentUserId == null || refreshing) return;
  refreshing = true;
  const requestedBy = currentUserId;
  fetchUnreadSummary()
    .then((summary) => {
      if (currentUserId !== requestedBy) return;
      const counts: Record<string, number> = {};
      for (const entry of summary.rooms) {
        if (entry.unread_count > 0) counts[entry.room] = entry.unread_count;
      }
      state = { ...state, counts, total: summary.total };
      emit();
    })
    .catch(() => {
      // Offline / transient: badges keep their last known values.
    })
    .finally(() => {
      refreshing = false;
    });
}

export function useUnread(): UnreadState {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

/**
 * Primitive selectors.
 *
 * `useUnread()` hands out the whole store, so a brand-new message (which only
 * touches the activity feed) re-rendered every consumer — Sidebar, chat rows,
 * dashboard. Selecting a single number lets React bail out when that number did
 * not actually change.
 */
export function useUnreadTotal(): number {
  return useSyncExternalStore(
    subscribe,
    () => state.total,
    () => state.total
  );
}

export function useUnreadCount(room: string): number {
  return useSyncExternalStore(
    subscribe,
    () => state.counts[room] ?? 0,
    () => state.counts[room] ?? 0
  );
}

