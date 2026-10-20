const RAW_BASE_URL = (import.meta.env.VITE_API_URL ?? "/api").trim();

/**
 * The API always goes through the same origin in production (`/api`).
 * Never fall back to a hardcoded `localhost` URL: on an HTTPS deployment the
 * browser would block it as mixed content and every request would fail with
 * "Failed to fetch".
 */
const BASE_URL = (() => {
  if (!RAW_BASE_URL || RAW_BASE_URL === "/") return "/api";
  return RAW_BASE_URL.replace(/\/+$/, "");
})();

function apiUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${BASE_URL}${normalized}`;
}

function clearSessionAndRedirect(): void {
  localStorage.removeItem("token");
  localStorage.removeItem("user");
  if (window.location.pathname !== "/login") {
    window.location.href = "/login";
  }
}

export type Role = "admin" | "editor" | "member";

export interface User {
  id: number;
  username: string;
  is_admin: boolean;
  role: Role;
  is_active: boolean;
  points: number;
  avatar_url?: string | null;
  bio?: string;
  last_seen?: string | null;
  created_at: string;
  code?: string;
}

export interface PublicUser {
  id: number;
  username: string;
  is_admin: boolean;
  role?: Role;
  points: number;
  avatar_url?: string | null;
}

export interface UserProfile {
  id: number;
  username: string;
  is_admin: boolean;
  role: Role;
  points: number;
  avatar_url?: string | null;
  bio: string;
  last_seen?: string | null;
  created_at: string;
}

export interface TeamMember {
  user: PublicUser;
  completed: boolean;
  is_self: boolean;
}

export interface ReplyPreview {
  id: number;
  sender_id: number;
  sender_username: string | null;
  content: string;
  file_url: string | null;
}

export interface Message {
  id: number;
  sender_id: number;
  sender_username: string | null;
  sender_avatar_url?: string | null;
  receiver_id: number | null;
  assignment_id: number | null;
  assignment_title?: string | null;
  content: string;
  file_url: string | null;
  reply_to: ReplyPreview | null;
  is_pinned: boolean;
  created_at: string;
}

export interface Attachment {
  id: number;
  assignment_id: number;
  user_id: number;
  user_username: string | null;
  uploader?: PublicUser | null;
  file_url: string;
  file_name: string;
  created_at: string;
}

export interface UploadResult {
  url: string;
  file_name: string;
  size: number;
}

export interface DirectPreview {
  peer_id: number;
  message: Message;
}

export interface ChatOverview {
  global_message: Message | null;
  directs: DirectPreview[];
}

export interface CompletedByUser {
  id: number;
  username: string | null;
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
  creator_id: number | null;
  creator_username: string | null;
  completed_by_users: CompletedByUser[];
  is_completed_by_me: boolean;
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

  const url = apiUrl(path);
  const method = options.method ?? "GET";

  let res: Response;
  try {
    res = await fetch(url, { ...options, headers });
  } catch (error) {
    console.error(`[api] ${method} ${url} failed before a response`, error);
    throw new Error("ارتباط با سرور برقرار نشد. اتصال اینترنت را بررسی کنید.", {
      cause: error,
    });
  }

  if (res.status === 401) {
    clearSessionAndRedirect();
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "خطا در ارتباط" }));
    console.error(`[api] ${method} ${url} -> ${res.status}`, err);
    throw new Error(typeof err.detail === "string" ? err.detail : "خطا");
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

// ---------- Auth ----------
export async function login(
  username: string,
  code?: string,
  password?: string
): Promise<LoginResponse> {
  const res = await fetch(apiUrl("/auth/login"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, code, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "خطا" }));
    throw new Error(err.detail || "خطا در ورود");
  }
  return res.json();
}

export async function register(
  username: string,
  password: string
): Promise<LoginResponse> {
  const res = await fetch(apiUrl("/auth/register"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "خطا" }));
    throw new Error(err.detail || "خطا در ثبت‌نام");
  }
  return res.json();
}

export async function fetchMe(): Promise<User> {
  return request<User>("/auth/me");
}

export async function fetchUserProfile(id: number): Promise<UserProfile> {
  return request<UserProfile>(`/users/${id}/profile`);
}

export async function updateMe(data: {
  avatar_url?: string | null;
  bio?: string;
}): Promise<User> {
  return request<User>("/users/me", {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteMyAvatar(): Promise<User> {
  return request<User>("/users/me/avatar", { method: "DELETE" });
}

// ---------- Users (admin) ----------
export async function fetchUsers(): Promise<User[]> {
  return request<User[]>("/users/");
}

export async function createUser(data: {
  username: string;
  code?: string;
  password?: string;
  is_admin?: boolean;
  role?: Role;
}): Promise<User> {
  return request<User>("/users/", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateUser(
  id: number,
  data: {
    username?: string;
    code?: string;
    password?: string;
    is_active?: boolean;
    role?: Role;
  }
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

export async function toggleAssignmentCompletion(
  id: number
): Promise<Assignment> {
  return request<Assignment>(`/assignments/${id}/toggle`, { method: "PATCH" });
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
  form.append("file", file, file.name);
  console.info("[assignment upload] POST", `/assignments/${assignmentId}/attachments`, {
    name: file.name,
    type: file.type,
    size: file.size,
  });
  try {
    return await request<Attachment>(`/assignments/${assignmentId}/attachments`, {
      method: "POST",
      body: form,
    });
  } catch (error) {
    console.error("[assignment upload] failed", {
      assignmentId,
      name: file.name,
      type: file.type,
      size: file.size,
      error,
    });
    throw error;
  }
}

export async function deleteAttachment(attachmentId: number): Promise<void> {
  return request<void>(`/attachments/${attachmentId}`, { method: "DELETE" });
}

// ---------- Team / leaderboard ----------
export async function fetchTeam(): Promise<PublicUser[]> {
  return request<PublicUser[]>("/users/team");
}

export async function fetchLeaderboard(): Promise<PublicUser[]> {
  return request<PublicUser[]>("/users/leaderboard");
}

// ---------- Chat ----------
export async function fetchChatOverview(signal?: AbortSignal): Promise<ChatOverview> {
  return request<ChatOverview>("/messages/overview", { signal });
}

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
  reply_to_id?: number | null;
}): Promise<Message> {
  return request<Message>("/messages/", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function deleteMessage(id: number): Promise<void> {
  return request<void>(`/messages/${id}`, { method: "DELETE" });
}

export async function clearChat(params: {
  scope: "global" | "private" | "assignment";
  peerId?: number;
  assignmentId?: number;
}): Promise<void> {
  const search = new URLSearchParams({ scope: params.scope });
  if (params.peerId) search.set("peer_id", String(params.peerId));
  if (params.assignmentId) search.set("assignment_id", String(params.assignmentId));
  return request<void>(`/messages/clear?${search.toString()}`, {
    method: "DELETE",
  });
}

export async function fetchRecentComments(limit = 5): Promise<Message[]> {
  return request<Message[]>(`/messages/recent-comments?limit=${limit}`);
}

export async function pinMessage(id: number): Promise<Message> {
  return request<Message>(`/messages/${id}/pin`, { method: "POST" });
}

export async function unpinMessage(id: number): Promise<Message> {
  return request<Message>(`/messages/${id}/pin`, { method: "DELETE" });
}

export const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;
const UPLOAD_TIMEOUT_MS = 5 * 60 * 1000;

export async function uploadFile(file: File): Promise<UploadResult> {
  const endpoint = apiUrl("/uploads/");

  if (file.size > MAX_UPLOAD_BYTES) {
    throw new Error("حجم فایل نباید بیشتر از ۲۵ مگابایت باشد.");
  }

  // Do NOT set Content-Type manually: the browser must add the multipart
  // boundary. `Authorization` is required — FastAPI rejects anonymous uploads.
  const form = new FormData();
  form.append("file", file, file.name);

  const token = getToken();
  const headers: Record<string, string> = { Accept: "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  console.info("[upload] POST", endpoint, {
    name: file.name,
    type: file.type,
    size: file.size,
    authenticated: Boolean(token),
  });

  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), UPLOAD_TIMEOUT_MS);

  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers,
      body: form,
      signal: controller.signal,
      credentials: "same-origin",
    });

    if (res.status === 401) {
      clearSessionAndRedirect();
      throw new Error("نشست شما منقضی شده است. دوباره وارد شوید.");
    }

    if (!res.ok) {
      const raw = await res.text().catch(() => "");
      let detail = "";
      try {
        const parsed = JSON.parse(raw) as { detail?: unknown };
        if (typeof parsed.detail === "string") detail = parsed.detail;
      } catch {
        /* non-JSON body (e.g. an Nginx 413 HTML page) */
      }
      console.error("[upload] failed", {
        endpoint,
        status: res.status,
        statusText: res.statusText,
        body: raw.slice(0, 500),
      });
      if (res.status === 413) {
        throw new Error(
          "حجم فایل از حد مجاز سرور بیشتر است (حداکثر ۲۵ مگابایت)."
        );
      }
      throw new Error(detail || `آپلود فایل ناموفق بود (HTTP ${res.status}).`);
    }

    const data = (await res.json()) as UploadResult;
    console.info("[upload] ok", data);
    return data;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      console.error("[upload] timed out", { endpoint, file: file.name });
      throw new Error("آپلود فایل بیش از حد طول کشید. دوباره تلاش کنید.", {
        cause: error,
      });
    }
    if (error instanceof TypeError) {
      console.error("[upload] network error (request never reached the API)", {
        endpoint,
        file: file.name,
        error,
      });
      throw new Error(
        "ارتباط با سرور برای آپلود برقرار نشد. احتمالاً حجم فایل از محدودیت پراکسی عبور کرده یا اتصال قطع شده است.",
        { cause: error }
      );
    }
    throw error instanceof Error ? error : new Error("آپلود فایل ناموفق بود");
  } finally {
    window.clearTimeout(timeout);
  }
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