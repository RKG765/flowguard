import { api, ApiError, setCsrfToken } from "./api";
import { hasRole, useAuth } from "./auth";
import { describe as describeMsg, engineFresh, useLive } from "./live";

function mockFetch(handler: (url: string, init: RequestInit) => { status: number; body?: unknown; headers?: Record<string, string> }) {
  const calls: { url: string; init: RequestInit }[] = [];
  globalThis.fetch = vi.fn(async (url: string | URL | Request, init: RequestInit = {}) => {
    calls.push({ url: String(url), init });
    const r = handler(String(url), init);
    return new Response(r.body === undefined ? null : JSON.stringify(r.body), { status: r.status, headers: r.headers });
  }) as unknown as typeof fetch;
  return calls;
}

afterEach(() => {
  setCsrfToken(null);
  vi.restoreAllMocks();
});

describe("api client", () => {
  it("sends the CSRF token on changes but not on reads", async () => {
    const calls = mockFetch(() => ({ status: 200, body: {} }));
    setCsrfToken("tok-1");
    await api("/api/x");
    await api("/api/y", { method: "POST", body: { a: 1 } });
    const h0 = calls[0]!.init.headers as Record<string, string>;
    const h1 = calls[1]!.init.headers as Record<string, string>;
    expect(h0["X-CSRF-Token"]).toBeUndefined();
    expect(h1["X-CSRF-Token"]).toBe("tok-1");
    expect(h1["Content-Type"]).toBe("application/json");
    expect(calls[1]!.init.credentials).toBe("same-origin");
  });

  it("turns error responses into ApiError with detail and Retry-After", async () => {
    mockFetch(() => ({ status: 429, body: { detail: "too many failed logins" }, headers: { "retry-after": "42" } }));
    await expect(api("/api/auth/login", { method: "POST", body: {} })).rejects.toMatchObject({ status: 429, detail: "too many failed logins", retryAfter: 42 });
  });

  it("reads FastAPI validation errors", async () => {
    mockFetch(() => ({ status: 422, body: { detail: [{ msg: "String should match pattern" }] } }));
    const err = (await api("/api/setup", { method: "POST", body: {} }).catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.detail).toBe("String should match pattern");
  });
});

describe("auth bootstrap", () => {
  beforeEach(() => useAuth.setState({ status: "loading", user: null }));

  it("goes to first-run setup when no user exists", async () => {
    mockFetch(() => ({ status: 200, body: { needs_setup: true } }));
    await useAuth.getState().bootstrap();
    expect(useAuth.getState().status).toBe("needs-setup");
  });

  it("goes to sign-in when there is no valid session", async () => {
    mockFetch((url) => (url.endsWith("/setup/status") ? { status: 200, body: { needs_setup: false } } : { status: 401, body: { detail: "authentication required" } }));
    await useAuth.getState().bootstrap();
    expect(useAuth.getState().status).toBe("anonymous");
  });

  it("restores an existing session and its CSRF token", async () => {
    const calls = mockFetch((url) =>
      url.endsWith("/setup/status") ? { status: 200, body: { needs_setup: false } } : url.endsWith("/auth/me") ? { status: 200, body: { id: 1, username: "admin", role: "admin", csrf_token: "c-9" } } : { status: 200, body: {} },
    );
    await useAuth.getState().bootstrap();
    expect(useAuth.getState().status).toBe("authenticated");
    await api("/api/x", { method: "POST" });
    expect((calls.at(-1)!.init.headers as Record<string, string>)["X-CSRF-Token"]).toBe("c-9");
  });

  it("reports offline when the core cannot be reached", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }) as unknown as typeof fetch;
    await useAuth.getState().bootstrap();
    expect(useAuth.getState().status).toBe("offline");
  });

  it("role ranks", () => {
    expect(hasRole({ id: 1, username: "a", role: "analyst" }, "viewer")).toBe(true);
    expect(hasRole({ id: 1, username: "a", role: "analyst" }, "admin")).toBe(false);
    expect(hasRole(null, "viewer")).toBe(false);
  });
});

describe("live stream", () => {
  beforeEach(() => useLive.setState({ feed: [], unseenAlerts: 0, engine: null, onAlert: null, onInvalidate: null }));

  it("describes alerts, restores and events in plain words", () => {
    const a = describeMsg({ type: "alert", data: { id: "x1", kind: "forged", severity: "high", dpid: "0000000000000001", table_id: 0, priority: 300, action: "removed", t: 1 } });
    expect(a?.text).toBe("forged on 0000000000000001 table 0 priority 300: removed");
    expect(describeMsg({ type: "alert_update", data: { alert_id: "x1", t: 2, timing: { time_to_restore_ms: 7.5 } } })?.text).toBe("Rule restored in 7.5 ms");
    expect(describeMsg({ type: "snapshot", data: {} })).toBeNull();
  });

  it("caps the feed, counts unseen alerts and asks for refetches", () => {
    const invalidated: string[] = [];
    const alerted: string[] = [];
    useLive.setState({ onInvalidate: (w) => invalidated.push(w), onAlert: (i) => alerted.push(i.key) });
    for (let i = 0; i < 80; i++) useLive.getState().ingest({ type: "alert", data: { id: `a${i}`, kind: "forged", severity: "high", t: i } });
    useLive.getState().ingest({ type: "snapshot", data: {} });
    const s = useLive.getState();
    expect(s.feed).toHaveLength(50);
    expect(s.unseenAlerts).toBe(80);
    expect(alerted).toHaveLength(80);
    expect(invalidated).toContain("rules");
    s.markSeen();
    expect(useLive.getState().unseenAlerts).toBe(0);
  });

  it("engine status freshness", () => {
    expect(engineFresh(null)).toBe(false);
    expect(engineFresh({ t: 100, switches: [], monitors_up: {}, epoch: 1, golden_rules: 0 }, 110)).toBe(true);
    expect(engineFresh({ t: 100, switches: [], monitors_up: {}, epoch: 1, golden_rules: 0 }, 130)).toBe(false);
  });
});
