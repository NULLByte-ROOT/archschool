const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";

export interface User {
  id: number;
  username: string;
  is_admin: boolean;
  is_active: boolean;
  points: number;
  created_at: string;
  code?: string;
}

export interface PublicUser {
  id: number;
  username: string;
  is_admin: boolean;
  points: number;
}

export interface TeamMember {
  user: PublicUser;
  completed: boolean;
  is_self: boolean;
}

export interface Message {
  id: number;
  sender_id: number;
  sender_username: string | null;
  receiver_id: number | null;
  assignment_id: number | null;
  content: string;
  file_url: string | null;
  created_at: string;
}

export interface Attachment {
  id: number;
  assignment_id: number;
  user_id: number;
  user_username: string | null;
  file_url: string;
  file_name: string;
  created_at: string;
}

export interface UploadResult {
  url: string;
  file_name: string;
  size: number;
}

export interface Assignment {
  id: number;
  title: string;
  description: string;
  course: string;
  category: string;
  subtype: string;
  subject_id: string;
  due_date: string | null;
  completed: boolean;
  owner_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

function getToken() {
  return localStorage.getItem("token");
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...((options.headers as Record<string, string>) || {}),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (
    options.body &&
    !(options.body instanceof FormData) &&
    !headers["Content-Type"]
  ) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });

  if (res.status === 401) {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    if (window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "خطا در ارتباط" }));
    throw new Error(typeof err.detail === "string" ? err.detail : "خطا");
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

// ---------- Auth ----------
export async function login(username: string, code: string): Promise<LoginResponse> {
  const res = await fetch(`${BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, code }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "خطا" }));
    throw new Error(err.detail || "خطا در ورود");
  }
  return res.json();
}

// ---------- Users (admin) ----------
export async function fetchUsers(): Promise<User[]> {
  return request<User[]>("/users/");
}

export async function createUser(data: {
  username: string;
  code?: string;
  is_admin?: boolean;
}): Promise<User> {
  return request<User>("/users/", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateUser(
  id: number,
  data: { username?: string; code?: string; is_active?: boolean }
): Promise<User> {
  return request<User>(`/users/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteUser(id: number): Promise<void> {
  return request<void>(`/users/${id}`, { method: "DELETE" });
}

// ---------- Assignments ----------
export async function fetchAssignments(
  params?: {
    completed?: boolean;
    course?: string;
  },
  signal?: AbortSignal
): Promise<Assignment[]> {
  const search = new URLSearchParams();
  if (params?.completed !== undefined) {
    search.set("completed", String(params.completed));
  }
  if (params?.course) search.set("course", params.course);
  const qs = search.toString();
  return request<Assignment[]>(`/assignments/${qs ? "?" + qs : ""}`, { signal });
}

export async function createAssignment(data: {
  title: string;
  description?: string;
  course?: string;
  category?: string;
  subtype?: string;
  subject_id?: string;
  due_date?: string | null;
  completed?: boolean;
}): Promise<Assignment> {
  return request<Assignment>("/assignments/", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function fetchAssignment(id: number): Promise<Assignment> {
  return request<Assignment>(`/assignments/${id}`);
}

export async function updateAssignment(
  id: number,
  data: Partial<Assignment>
): Promise<Assignment> {
  return request<Assignment>(`/assignments/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteAssignment(id: number): Promise<void> {
  return request<void>(`/assignments/${id}`, { method: "DELETE" });
}

export async function fetchTeamStatus(assignmentId: number): Promise<TeamMember[]> {
  return request<TeamMember[]>(`/assignments/${assignmentId}/team`);
}

export async function fetchAttachments(assignmentId: number): Promise<Attachment[]> {
  return request<Attachment[]>(`/assignments/${assignmentId}/attachments`);
}

export async function uploadAssignmentFile(
  assignmentId: number,
  file: File
): Promise<Attachment> {
  const form = new FormData();
  form.append("file", file);
  return request<Attachment>(`/assignments/${assignmentId}/attachments`, {
    method: "POST",
    body: form,
  });
}

// ---------- Team / leaderboard ----------
export async function fetchTeam(): Promise<PublicUser[]> {
  return request<PublicUser[]>("/users/team");
}

export async function fetchLeaderboard(): Promise<PublicUser[]> {
  return request<PublicUser[]>("/users/leaderboard");
}

// ---------- Chat ----------
export async function fetchMessages(params: {
  scope: "global" | "private" | "assignment";
  peerId?: number;
  assignmentId?: number;
  limit?: number;
}): Promise<Message[]> {
  const search = new URLSearchParams({ scope: params.scope });
  if (params.peerId) search.set("peer_id", String(params.peerId));
  if (params.assignmentId) search.set("assignment_id", String(params.assignmentId));
  if (params.limit) search.set("limit", String(params.limit));
  return request<Message[]>(`/messages/?${search.toString()}`);
}

export async function sendMessage(data: {
  content?: string;
  receiver_id?: number | null;
  assignment_id?: number | null;
  file_url?: string | null;
}): Promise<Message> {
  return request<Message>("/messages/", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function uploadFile(file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  return request<UploadResult>("/uploads/", { method: "POST", body: form });
}

export function resolveMediaUrl(url: string | null | undefined): string {
  if (!url) return "";
  if (/^https?:\/\//i.test(url)) return url;
  const api = new URL(BASE_URL, window.location.origin);
  const mixedContent =
    window.location.protocol === "https:" && api.protocol === "http:";
  const origin = mixedContent ? window.location.origin : api.origin;
  return new URL(url, origin).toString();
}

/**
 * Builds the WebSocket URL from the current page, so it automatically uses
 * `wss://` on HTTPS and `ws://` on HTTP, on localhost and in production.
 */
export function getWebSocketUrl(room: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const url = new URL(`${protocol}//${window.location.host}/api/ws`);
  url.searchParams.set("token", getToken() ?? "");
  url.searchParams.set("room", room);
  return url.toString();
}