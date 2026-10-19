const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";

export interface User {
  id: number;
  username: string;
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
  code?: string;
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
  if (options.body && !headers["Content-Type"]) {
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