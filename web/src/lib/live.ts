import { create } from "zustand";
import { api } from "./api";

/** Live stream from the core: POST /api/auth/ws-ticket, then ws(s)://<host>/api/ws?ticket=... (one-time ticket, so the
 *  session token never appears in a URL). Reconnects with backoff. Messages: hello | alert | alert_update | snapshot |
 *  engine_status | event. Only the newest 50 feed items are kept so a burst of alerts cannot grow memory. */

export interface FeedItem { key: string; t: number; type: string; kind: string; severity: string; text: string; dpid?: string | null; alertId?: string }
export interface LiveEngineStatus { t: number; switches: string[]; monitors_up: Record<string, boolean>; epoch: number; golden_rules: number }

interface LiveState {
  socket: "idle" | "connecting" | "open" | "closed";
  engine: LiveEngineStatus | null;
  feed: FeedItem[];
  unseenAlerts: number;
  lastMessageAt: number | null;
  onAlert: ((item: FeedItem) => void) | null;
  onInvalidate: ((what: string) => void) | null;
  connect: () => void;
  disconnect: () => void;
  markSeen: () => void;
  ingest: (msg: { type: string; data: Record<string, unknown> }) => void;
}

const FEED_MAX = 50;
let ws: WebSocket | null = null;
let stopped = true;
let backoff = 1000;
let timer: ReturnType<typeof setTimeout> | null = null;

const str = (v: unknown): string => (v === undefined || v === null ? "" : String(v));

export function describe(msg: { type: string; data: Record<string, unknown> }): FeedItem | null {
  const d = msg.data ?? {};
  const t = typeof d.t === "number" ? d.t : Date.now() / 1000;
  if (msg.type === "alert") {
    const where = d.priority !== undefined && d.priority !== null ? ` table ${str(d.table_id)} priority ${str(d.priority)}` : "";
    return { key: `a-${str(d.id)}`, t, type: "alert", kind: str(d.kind), severity: str(d.severity) || "medium",
             text: `${str(d.kind).replace(/_/g, " ")} on ${str(d.dpid) || "FlowGuard"}${where}: ${str(d.action) || "no action"}`,
             dpid: (d.dpid as string) ?? null, alertId: str(d.id) };
  }
  if (msg.type === "alert_update") {
    const ms = (d.timing as Record<string, unknown> | undefined)?.time_to_restore_ms;
    return { key: `u-${str(d.alert_id)}`, t, type: "alert_update", kind: "restored", severity: "info",
             text: `Rule restored${ms !== undefined ? ` in ${ms} ms` : ""}`, alertId: str(d.alert_id) };
  }
  if (msg.type === "event") {
    return { key: `e-${t}-${str(d.kind)}`, t, type: "event", kind: str(d.kind), severity: "info",
             text: `${str(d.kind).replace(/_/g, " ")}${d.dpid ? ` (${str(d.dpid)})` : ""}`, dpid: (d.dpid as string) ?? null };
  }
  return null;
}

export const useLive = create<LiveState>((set, get) => ({
  socket: "idle",
  engine: null,
  feed: [],
  unseenAlerts: 0,
  lastMessageAt: null,
  onAlert: null,
  onInvalidate: null,

  ingest(msg) {
    set({ lastMessageAt: Date.now() });
    if (msg.type === "engine_status") {
      const d = msg.data as unknown as LiveEngineStatus;
      set({ engine: { t: d.t, switches: d.switches ?? [], monitors_up: d.monitors_up ?? {}, epoch: d.epoch, golden_rules: d.golden_rules } });
      return;
    }
    if (msg.type === "snapshot") {
      get().onInvalidate?.("rules");
      return;
    }
    const item = describe(msg);
    if (!item) return;
    set((s) => ({ feed: [item, ...s.feed.filter((f) => f.key !== item.key)].slice(0, FEED_MAX),
                  unseenAlerts: s.unseenAlerts + (item.type === "alert" ? 1 : 0) }));
    if (item.type === "alert") {
      get().onAlert?.(item);
      get().onInvalidate?.("alerts");
    }
    if (item.type === "alert_update") get().onInvalidate?.("alerts");
  },

  connect() {
    if (!stopped && ws) return;
    stopped = false;
    const open = async () => {
      if (stopped) return;
      set({ socket: "connecting" });
      try {
        const { ticket } = await api<{ ticket: string }>("/api/auth/ws-ticket", { method: "POST" });
        const proto = window.location.protocol === "https:" ? "wss" : "ws";
        ws = new WebSocket(`${proto}://${window.location.host}/api/ws?ticket=${encodeURIComponent(ticket)}`);
        ws.onopen = () => {
          backoff = 1000;
          set({ socket: "open" });
        };
        ws.onmessage = (ev) => {
          try {
            get().ingest(JSON.parse(String(ev.data)));
          } catch {
            /* ignore malformed frames */
          }
        };
        ws.onclose = () => {
          ws = null;
          set({ socket: "closed" });
          if (!stopped) timer = setTimeout(open, backoff);
          backoff = Math.min(backoff * 2, 15000);
        };
      } catch {
        set({ socket: "closed" });
        if (!stopped) timer = setTimeout(open, backoff);
        backoff = Math.min(backoff * 2, 15000);
      }
    };
    void open();
  },

  disconnect() {
    stopped = true;
    if (timer) clearTimeout(timer);
    ws?.close();
    ws = null;
    set({ socket: "idle" });
  },

  markSeen() {
    set({ unseenAlerts: 0 });
  },
}));

/** Engine counts as "connected" when its periodic status (every 5 s) is fresh. */
export const engineFresh = (e: LiveEngineStatus | null, nowSec: number = Date.now() / 1000): boolean => !!e && nowSec - e.t < 15;
