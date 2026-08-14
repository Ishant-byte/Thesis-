const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";
const SESSION_STORAGE_KEY = "pramaanhr_session";
const LOGOUT_REASON_STORAGE_KEY = "pramaanhr_logout_reason";
const LOGOUT_REASONS: Record<string, string> = {
  "This account is inactive.": "Your account has been deactivated. Contact an administrator.",
  "This account no longer exists.": "This account is no longer available.",
};
const EXPIRED_SESSION_REASON = "Your session has expired. Please sign in again.";
export const AUTH_LOGOUT_EVENT = "pramaanhr:auth-logout";

export interface AuthLogoutEventDetail {
  reason: string;
  redirectPath: string;
}

export class APIError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "APIError";
  }
}

async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(input, init);
  } catch (e) {
    if (e instanceof DOMException && e.name === "TimeoutError") {
      throw new APIError("The application server did not respond.");
    }
    throw new APIError("Cannot reach the application server. Check that MongoDB and PramaanHR are running.");
  }
}

function getLoginRedirectPath(): string {
  try {
    const raw = sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) return "/";
    const parsed = JSON.parse(raw) as { role?: string };
    return parsed.role === "employee" ? "/login/employee" : "/login/admin";
  } catch {
    return "/";
  }
}

function handleProtectedAuthFailure(status: number, detail: string, hadToken: boolean): void {
  if (!hadToken || status !== 401) return;
  const redirectPath = getLoginRedirectPath();
  const reason = LOGOUT_REASONS[detail] ?? EXPIRED_SESSION_REASON;
  sessionStorage.setItem(LOGOUT_REASON_STORAGE_KEY, reason);
  sessionStorage.removeItem(SESSION_STORAGE_KEY);
  window.dispatchEvent(
    new CustomEvent<AuthLogoutEventDetail>(AUTH_LOGOUT_EVENT, { detail: { reason, redirectPath } })
  );
}

export function consumeLogoutReason(): string {
  const reason = sessionStorage.getItem(LOGOUT_REASON_STORAGE_KEY) ?? "";
  sessionStorage.removeItem(LOGOUT_REASON_STORAGE_KEY);
  return reason;
}

function getErrorDetail(statusText: string, contentType: string, body: string): string {
  let detail = statusText;
  if (!body) return detail;
  if (contentType.includes("application/json")) {
    try {
      const j = JSON.parse(body) as { detail?: unknown };
      return typeof j.detail === "string" ? j.detail : body;
    } catch {
      return body;
    }
  }
  return body;
}

async function handleResponse(r: Response, hadToken = false): Promise<unknown> {
  const ct = r.headers.get("content-type") ?? "";
  const body = await r.text();

  if (r.status >= 400) {
    const detail = getErrorDetail(r.statusText, ct, body);
    handleProtectedAuthFailure(r.status, detail, hadToken);
    throw new APIError(String(detail));
  }
  if (ct.includes("application/json")) return body ? JSON.parse(body) : null;
  return body;
}

function headers(token?: string): HeadersInit {
  const h: HeadersInit = { "Content-Type": "application/json" };
  if (token) h["Authorization"] = `Bearer ${token}`;
  return h;
}

export async function health(): Promise<{ ok: boolean; time: string }> {
  const r = await apiFetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(3000) });
  return handleResponse(r) as Promise<{ ok: boolean; time: string }>;
}

export async function get<T = unknown>(path: string, token?: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(`${API_BASE}${path}`, window.location.origin);
  if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
  const h: HeadersInit = {};
  if (token) h["Authorization"] = `Bearer ${token}`;
  const r = await apiFetch(url.toString(), { headers: h });
  return handleResponse(r, Boolean(token)) as Promise<T>;
}

export async function post<T = unknown>(path: string, payload: unknown, token?: string): Promise<T> {
  const r = await apiFetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: headers(token),
    body: JSON.stringify(payload),
  });
  return handleResponse(r, Boolean(token)) as Promise<T>;
}

export async function put<T = unknown>(path: string, payload: unknown, token: string): Promise<T> {
  const r = await apiFetch(`${API_BASE}${path}`, {
    method: "PUT",
    headers: headers(token),
    body: JSON.stringify(payload),
  });
  return handleResponse(r, true) as Promise<T>;
}

export async function del(path: string, token: string): Promise<void> {
  const r = await apiFetch(`${API_BASE}${path}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  await handleResponse(r, true);
}

export async function downloadBlob(path: string, token: string): Promise<Blob> {
  const r = await apiFetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (r.status >= 400) {
    const body = await r.text();
    const detail = getErrorDetail(r.statusText, r.headers.get("content-type") ?? "", body);
    handleProtectedAuthFailure(r.status, detail, true);
    throw new APIError(String(detail));
  }
  return r.blob();
}

export function wsUrl(token: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = import.meta.env.VITE_WS_HOST ?? window.location.host;
  const base = import.meta.env.VITE_WS_BASE;
  if (base) return `${base}?token=${encodeURIComponent(token)}`;
  return `${proto}//${host}/ws?token=${encodeURIComponent(token)}`;
}

export function downloadBase64File(data: string, filename: string, type = "application/x-pkcs12"): void {
  const binary = atob(data);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  const url = URL.createObjectURL(new Blob([bytes], { type }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
