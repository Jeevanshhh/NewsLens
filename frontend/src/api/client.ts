// Thin typed wrapper around the FastAPI backend using fetch.
// No external HTTP dependency keeps the install surface small.

import type {
  AnalyticsOverview,
  Article,
  ArticlesList,
  BookmarkItem,
  ExportFormat,
  LiveHeadlines,
  SearchHistoryList,
  SearchParams,
  SearchRunResult,
  TokenResponse,
  User,
} from "./types";

const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";
const TOKEN_KEY = "newslens.token";

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

// ---- token storage --------------------------------------------------------
export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  params?: Record<string, string | number | boolean | null | undefined>;
  auth?: boolean;
}

function buildQuery(params?: RequestOptions["params"]): string {
  if (!params) return "";
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") usp.set(k, String(v));
  }
  const s = usp.toString();
  return s ? `?${s}` : "";
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, params, auth = true } = opts;
  const headers: Record<string, string> = {};
  const token = getToken();
  if (auth && token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const res = await fetch(`${BASE}/api${path}${buildQuery(params)}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 204) return undefined as T;

  const text = await res.text();
  const data = text ? safeJson(text) : null;
  if (!res.ok) {
    const detail =
      (data && typeof data === "object" && "detail" in data
        ? String((data as { detail: unknown }).detail)
        : null) ?? `Request failed (${res.status})`;
    throw new ApiError(res.status, detail);
  }
  return data as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

// ---- auth -----------------------------------------------------------------
export const auth = {
  register: (name: string, email: string, password: string) =>
    request<TokenResponse>("/auth/register", {
      method: "POST",
      body: { name, email, password },
      auth: false,
    }),
  login: (email: string, password: string) =>
    request<TokenResponse>("/auth/login", {
      method: "POST",
      body: { email, password },
      auth: false,
    }),
  me: () => request<User>("/auth/me"),
  changePassword: (currentPassword: string, newPassword: string) =>
    request<void>("/auth/change-password", {
      method: "POST",
      body: { current_password: currentPassword, new_password: newPassword },
    }),
  requestPasswordReset: (email: string) =>
    request<{ detail: string }>("/auth/password-reset/request", {
      method: "POST",
      body: { email },
      auth: false,
    }),
  confirmPasswordReset: (token: string, newPassword: string) =>
    request<void>("/auth/password-reset/confirm", {
      method: "POST",
      body: { token, new_password: newPassword },
      auth: false,
    }),
  deleteAccount: () => request<void>("/auth/account", { method: "DELETE" }),
};

// ---- search + articles ----------------------------------------------------
export const search = {
  run: (params: SearchParams) =>
    request<SearchRunResult>("/search", { method: "POST", body: params }),
  history: (savedOnly = false) =>
    request<SearchHistoryList>("/searches", { params: { saved_only: savedOnly } }),
  save: (id: number, name?: string) =>
    request<{ id: number; is_saved: boolean; name: string | null }>(
      `/searches/${id}/save`,
      { method: "POST", params: { name } },
    ),
  unsave: (id: number) =>
    request<{ id: number; is_saved: boolean }>(`/searches/${id}/unsave`, {
      method: "POST",
    }),
  remove: (id: number) =>
    request<{ deleted: boolean }>(`/searches/${id}`, { method: "DELETE" }),
};

export const articles = {
  list: (params: {
    provider?: string;
    category?: string;
    state?: string;
    q?: string;
    search_id?: number;
    sort?: string;
    page?: number;
    page_size?: number;
  }) => request<ArticlesList>("/articles", { params }),
  detail: (id: number) => request<Article>(`/articles/${id}`),
  related: (id: number, limit = 6) =>
    request<{ items: Article[]; count: number }>(`/articles/${id}/related`, {
      params: { limit },
    }),
};

// ---- live brief -----------------------------------------------------------
export const news = {
  live: (limit = 8) => request<LiveHeadlines>("/news/live", { params: { limit } }),
};

// ---- bookmarks ------------------------------------------------------------
export const bookmarks = {
  list: () => request<{ items: BookmarkItem[]; count: number }>("/bookmarks"),
  add: (articleId: number) =>
    request<{ created: boolean; bookmark: BookmarkItem }>("/bookmarks", {
      method: "POST",
      body: { article_id: articleId },
    }),
  remove: (articleId: number) =>
    request<{ deleted: boolean }>(`/bookmarks/${articleId}`, { method: "DELETE" }),
  status: (ids: number[]) =>
    request<{ status: Record<string, boolean> }>("/bookmarks/status", {
      params: { ids: ids.join(",") },
    }),
};

// ---- analytics + export ---------------------------------------------------
export const analytics = {
  overview: (params?: { provider?: string; category?: string; state?: string }) =>
    request<AnalyticsOverview>("/analytics", { params }),
};

export function exportUrl(params: {
  format: ExportFormat;
  search_id?: number;
  provider?: string;
  category?: string;
  state?: string;
  q?: string;
  sort?: string;
}): string {
  return `/api/export${buildQuery(params)}`;
}

// Downloads an export through fetch so the Authorization header is attached,
// then triggers a browser save via a transient object URL.
export async function downloadExport(params: {
  format: ExportFormat;
  search_id?: number;
  provider?: string;
  category?: string;
  state?: string;
  q?: string;
  sort?: string;
}): Promise<void> {
  const res = await fetch(`${BASE}${exportUrl(params)}`, {
    headers: getToken() ? { Authorization: `Bearer ${getToken()}` } : {},
  });
  if (!res.ok) {
    throw new ApiError(res.status, `Export failed (${res.status})`);
  }
  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = /filename="?([^\";]+)"?/.exec(disposition);
  const filename = match ? match[1] : `newslens-export.${params.format}`;

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// Download the caller's own personal data (profile, searches, bookmarks,
// reports) as JSON - the data-portability export behind Settings.
export async function downloadMyData(): Promise<void> {
  const res = await fetch(`${BASE}/api/auth/me/data`, {
    headers: getToken() ? { Authorization: `Bearer ${getToken()}` } : {},
  });
  if (!res.ok) {
    throw new ApiError(res.status, `Export failed (${res.status})`);
  }
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = /filename="?([^";]+)"?/.exec(disposition);
  const filename = match ? match[1] : "newslens-my-data.json";
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
