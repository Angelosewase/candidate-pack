export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Role = "client" | "operator" | "admin";
export type RequestStatus =
  | "submitted"
  | "in_progress"
  | "delivered"
  | "accepted"
  | "rejected";
export type Quality = "good" | "usable" | "bad";

export interface User {
  id: number;
  email: string;
  name: string;
  organisation: string | null;
  role: Role;
  is_active: boolean;
  created_at: string;
}

export interface StatusEvent {
  id: number;
  from_status: RequestStatus | null;
  to_status: RequestStatus;
  actor: { id: number; name: string; organisation: string | null; role: Role };
  note: string | null;
  created_at: string;
}

export interface DatasetRequest {
  id: number;
  client: { id: number; name: string; organisation: string | null; role: Role };
  task_name: string;
  episodes_requested: number;
  deadline: string;
  notes: string;
  status: RequestStatus;
  created_at: string;
  updated_at: string;
  assigned_count: number;
  allowed_transitions: RequestStatus[];
}

export interface RequestDetail extends DatasetRequest {
  events: StatusEvent[];
}

export interface Episode {
  episode_id: string;
  robot_id: string;
  task_name: string;
  recorded_at: string;
  duration_seconds: number | null;
  operator_name: string | null;
  quality: Quality;
  assigned_request_id: number | null;
}

export interface Assignment {
  episode: Episode;
  assigned_at: string;
  assigned_by: number;
}

export interface Page<T> {
  items: T[];
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface Analytics {
  date_from: string;
  date_to: string;
  episodes_per_day: { day: string; robot_id: string; episodes: number }[];
  request_fulfilment: {
    by_status: Record<RequestStatus, number>;
    total: number;
    delivered_count: number;
    median_hours_submitted_to_delivered: number | null;
  };
  top_tasks_by_good_episodes: { task_name: string; good_episodes: number }[];
}

export class ApiError extends Error {
  status: number;
  details: unknown;
  constructor(status: number, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("desk.token");
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem("desk.token", token);
  else window.localStorage.removeItem("desk.token");
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      ...(options.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers ?? {}),
    },
  });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(
      res.status,
      (body as { message?: string }).message ??
        (body as { error?: string }).error ??
        `Request failed (${res.status})`,
      (body as { details?: unknown }).details,
    );
  }
  return body as T;
}

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string; user: User }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<User>("/auth/me"),
  listRequests: (params: { status?: string; limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.status) q.set("status", params.status);
    q.set("limit", String(params.limit ?? 50));
    q.set("offset", String(params.offset ?? 0));
    return request<Page<DatasetRequest>>(`/requests?${q}`);
  },
  createRequest: (body: {
    task_name: string;
    episodes_requested: number;
    deadline: string;
    notes?: string;
  }) =>
    request<RequestDetail>("/requests", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getRequest: (id: number) => request<RequestDetail>(`/requests/${id}`),
  transition: (id: number, to_status: RequestStatus, note?: string) =>
    request<RequestDetail>(`/requests/${id}/transitions`, {
      method: "POST",
      body: JSON.stringify({ to_status, note: note || undefined }),
    }),
  listAssignments: (id: number) =>
    request<Assignment[]>(`/requests/${id}/assignments`),
  assign: (id: number, episode_ids: string[]) =>
    request<Assignment[]>(`/requests/${id}/assignments`, {
      method: "POST",
      body: JSON.stringify({ episode_ids }),
    }),
  unassign: (id: number, episode_id: string) =>
    request<void>(
      `/requests/${id}/assignments/${encodeURIComponent(episode_id)}`,
      { method: "DELETE" },
    ),
  listEpisodes: (params: {
    task_name?: string;
    quality?: string;
    assignable_only?: boolean;
    limit?: number;
    offset?: number;
  } = {}) => {
    const q = new URLSearchParams();
    if (params.task_name) q.set("task_name", params.task_name);
    if (params.quality) q.set("quality", params.quality);
    if (params.assignable_only) q.set("assignable_only", "true");
    q.set("limit", String(params.limit ?? 50));
    q.set("offset", String(params.offset ?? 0));
    return request<Page<Episode>>(`/episodes?${q}`);
  },
  importCsv: async (file: File) => {
    const token = getToken();
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API_URL}/import`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new ApiError(
        res.status,
        (body as { message?: string }).message ?? `Import failed (${res.status})`,
        (body as { details?: unknown }).details,
      );
    }
    return body as {
      import_id: number;
      total_rows: number;
      inserted: number;
      updated: number;
      unchanged: number;
      skipped: number;
      skipped_by_reason: Record<string, number>;
      skipped_rows: { row: number; episode_id: string | null; reason: string; detail: string }[];
      warnings: { row: number; episode_id: string | null; reason: string; detail: string }[];
    };
  },
  listImports: () => request<{ id: number; filename: string; total_rows: number; inserted: number; updated: number; unchanged: number; skipped: number; created_at: string }[]>("/imports"),
  analytics: (date_from: string, date_to: string) =>
    request<Analytics>(
      `/analytics?date_from=${date_from}&date_to=${date_to}`,
    ),
  listUsers: () => request<User[]>("/users"),
  createUser: (body: {
    email: string;
    name: string;
    password: string;
    role: Role;
    organisation?: string;
  }) =>
    request<User>("/users", { method: "POST", body: JSON.stringify(body) }),
  updateUser: (id: number, body: Partial<{ name: string; organisation: string; role: Role; is_active: boolean; password: string }>) =>
    request<User>(`/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
};
