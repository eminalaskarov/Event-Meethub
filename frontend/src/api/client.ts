import i18n from "../i18n";

const API_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1").replace(/\/$/, "");
const TOKEN_KEY = "eventhub.token";

export const WS_URL = API_URL.replace(/^http/, "ws");
export const UNAUTHORIZED_EVENT = "eventhub:unauthorized";

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message);
  }
}

function parseError(body: unknown, status: number): ApiError {
  const detail = (body as { detail?: unknown } | null)?.detail;

  if (typeof detail === "string") return new ApiError(detail, status);

  if (Array.isArray(detail)) {
    const details = detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join(", ");
    return new ApiError(
      details ? i18n.t("errors.invalidDataWith", { details }) : i18n.t("errors.invalidData"),
      status,
    );
  }

  if (detail && typeof detail === "object") {
    const value = detail as { code?: string; message?: string };
    const key = `errors.codes.${value.code}`;
    const message =
      value.code && i18n.exists(key)
        ? i18n.t(key)
        : value.message ?? i18n.t("errors.requestFailed", { status });
    return new ApiError(message, status, value.code);
  }

  return new ApiError(i18n.t("errors.requestFailed", { status }), status);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = tokenStore.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (response.status === 204) return undefined as T;

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && token) {
      tokenStore.clear();
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
    throw parseError(body, response.status);
  }
  return body as T;
}

function jsonRequest<T>(method: string, path: string, data?: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: data === undefined ? undefined : { "Content-Type": "application/json" },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, data?: unknown) => jsonRequest<T>("POST", path, data),
  patch: <T>(path: string, data: unknown) => jsonRequest<T>("PATCH", path, data),
  delete: <T>(path: string) => jsonRequest<T>("DELETE", path),
  login: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: new URLSearchParams({ username: email, password }),
    }),
};

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : i18n.t("errors.generic");
}