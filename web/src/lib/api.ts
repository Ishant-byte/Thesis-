const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

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
      throw new APIError("API server did not respond. Start the backend with: python -m server.app");
    }
    throw new APIError("Cannot reach API server. Start MongoDB, then run: python -m server.app");
  }
}

async function handleResponse(r: Response): Promise<unknown> {
  const ct = r.headers.get("content-type") ?? "";
  const body = await r.text();

  if (r.status >= 400) {
    let detail = r.statusText;
    if (body) {
      if (ct.includes("application/json")) {
        try {
          const j = JSON.parse(body) as { detail?: unknown };
          detail = typeof j.detail === "string" ? j.detail : body;
        } catch {
          detail = body;
        }
      } else {
        detail = body;
      }
    }
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
  return handleResponse(r) as Promise<T>;
}

export async function post<T = unknown>(path: string, payload: unknown, token?: string): Promise<T> {
  const r = await apiFetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: headers(token),
    body: JSON.stringify(payload),
  });
  return handleResponse(r) as Promise<T>;
}

export async function put<T = unknown>(path: string, payload: unknown, token: string): Promise<T> {
  const r = await apiFetch(`${API_BASE}${path}`, {
    method: "PUT",
    headers: headers(token),
    body: JSON.stringify(payload),
  });
  return handleResponse(r) as Promise<T>;
}

export async function del(path: string, token: string): Promise<void> {
  const r = await apiFetch(`${API_BASE}${path}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  await handleResponse(r);
}

export async function downloadBlob(path: string, token: string): Promise<Blob> {
  const r = await apiFetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (r.status >= 400) {
    let detail = r.statusText;
    const body = await r.text();
    if (body) {
      try {
        const j = JSON.parse(body) as { detail?: unknown };
        detail = typeof j.detail === "string" ? j.detail : body;
      } catch {
        detail = body;
      }
    }
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
