/** Minimal typed client for the FlowGuard core API (same origin; the session lives in an HttpOnly cookie).
 *  The CSRF token returned by login / GET /api/auth/me is kept in memory only and sent on every state change. */

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
    public readonly retryAfter: number | null = null,
  ) {
    super(detail);
  }
}

let csrfToken: string | null = null;
export const setCsrfToken = (t: string | null): void => {
  csrfToken = t;
};

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export async function api<T>(path: string, opts: { method?: Method; body?: unknown; signal?: AbortSignal } = {}): Promise<T> {
  const method = opts.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json" };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET" && csrfToken) headers["X-CSRF-Token"] = csrfToken;
  const res = await fetch(path, {
    method,
    headers,
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    credentials: "same-origin",
    signal: opts.signal,
  });
  if (!res.ok) {
    let detail = res.statusText || `HTTP ${res.status}`;
    try {
      const j = await res.json();
      if (typeof j?.detail === "string") detail = j.detail;
      else if (Array.isArray(j?.detail) && j.detail[0]?.msg) detail = String(j.detail[0].msg);
    } catch {
      /* not JSON */
    }
    const ra = res.headers.get("retry-after");
    throw new ApiError(res.status, detail, ra ? Number(ra) : null);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/* ---- response shapes used by the shell and the Overview (see core/api/*.py) ---------------------------------- */
export type Role = "viewer" | "analyst" | "admin";
export interface Me { id: number; username: string; role: Role; csrf_token: string }
export interface LoginResponse { csrf_token: string; expires_at: number; user: { id: number; username: string; role: Role } }
export interface RulesSummary { rules: number; protected: number; verified: number; verified_percent: number | null; by_status: Record<string, number>; as_of: number | null }
export interface Stat { n: number; mean: number; median: number; p95: number }
export interface ReportSummary { alerts_total: number; alerts_by_kind: Record<string, number>; open_incidents: number; detect_latency_ms: Stat | null; time_to_restore_ms: Stat | null }
export interface Incident { id: number; title: string; severity: string; status: "open" | "acknowledged" | "closed"; dpid: string | null; alert_count: number; updated_at: number }
export interface Page<T> { total: number; items: T[] }
export interface EngineEvent { id: number; t: number; kind: string; dpid: string | null; data: Record<string, unknown> }
export interface EngineStatus { known: boolean; age_seconds?: number | null; stale?: boolean; status?: { switches: string[]; monitors_up: Record<string, boolean>; epoch: number; golden_rules: number } }
