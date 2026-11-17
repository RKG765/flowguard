import { create } from "zustand";

/* Demo Lab state: a SIMULATED four-switch network, entirely in the browser. Nothing here talks to the core, an engine or
   a switch (ADR-019: FlowGuard executes no attacks). "Simulating tampering" only edits this in-memory model and then
   shows what FlowGuard's L1 check would report: the kind, how fast, signed vs found, and the repair. */

export type Kind = "altered" | "forged" | "missing" | "shadow" | "unattributed_change";
export interface SimRule {
  id: string;
  sw: string;
  table: number;
  priority: number;
  match: string;
  signed: string | null;
  found: string | null;
  signedCookie: string | null;
  foundCookie: string | null;
  status: "ok" | Kind;
}
export interface SimEvent {
  id: number;
  t: number;
  kind: Kind;
  sw: string;
  ruleId: string;
  detectMs: number;
  restoreMs: number | null;
  summary: string;
  signed: string | null;
  found: string | null;
  signedCookie: string | null;
  foundCookie: string | null;
}

export const SWITCHES = [
  { id: "s1", name: "core", x: 300, y: 100, hosts: [] as string[] },
  { id: "s2", name: "edge-west", x: 120, y: 205, hosts: ["h1", "h2"] },
  { id: "s3", name: "edge-mid", x: 300, y: 205, hosts: ["h3", "h4"] },
  { id: "s4", name: "edge-east", x: 480, y: 205, hosts: ["h5", "h6"] },
];
export const LINKS: [string, string][] = [["s1", "s2"], ["s1", "s3"], ["s1", "s4"], ["s2", "s3"]];

const TEMPLATE = [
  { table: 0, priority: 100, match: "tcp_dst=23", signed: "drop" },
  { table: 0, priority: 90, match: "eth_type=0x0806", signed: "output:FLOOD" },
  { table: 1, priority: 50, match: "ipv4_dst=10.0.0.0/24", signed: "output:2" },
  { table: 0, priority: 0, match: "any packet", signed: "goto_table:1" },
];

/** Deterministic 16-hex "HMAC cookie" for a rule, so the stripe is stable between runs. */
export function fakeCookie(seed: string): string {
  let h = 2166136261;
  let out = "";
  for (let i = 0; i < 16; i++) {
    for (const ch of seed + i) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
    out += ((h >>> 0) & 15).toString(16);
  }
  return out;
}

export function freshRules(): SimRule[] {
  return SWITCHES.flatMap((s) =>
    TEMPLATE.map((t, i) => {
      const c = fakeCookie(`${s.id}-${i}`);
      return { ...t, id: `${s.id}-r${i + 1}`, sw: s.id, found: t.signed, signedCookie: c, foundCookie: c, status: "ok" as const };
    }),
  );
}

const ALTERED_ACTION: Record<string, string> = { drop: "output:3", "output:FLOOD": "drop", "output:2": "output:99", "goto_table:1": "drop" };

/** Pure: applies one tampering kind to one rule and returns the new rule list plus the detection event. */
export function tamper(rules: SimRule[], kind: Kind, ruleId: string, now: number, rnd: () => number = Math.random): { rules: SimRule[]; event: Omit<SimEvent, "id"> } {
  const base = rules.find((r) => r.id === ruleId)!;
  const detectMs = Math.round(6 + rnd() * 30);
  const flip = (c: string) => c.slice(0, 12) + fakeCookie(c).slice(0, 4);
  if (kind === "altered" || kind === "unattributed_change") {
    const found = ALTERED_ACTION[base.signed ?? ""] ?? "drop";
    const foundCookie = flip(base.signedCookie!);
    const summary = kind === "altered" ? `Signed rule on ${base.sw} now does "${found}" instead of "${base.signed}"` : `Rule on ${base.sw} was changed and changed back (tamper-and-revert)`;
    const rules2 = rules.map((r) => (r.id === ruleId ? { ...r, found, foundCookie, status: kind } : r));
    return { rules: rules2, event: { t: now, kind, sw: base.sw, ruleId, detectMs, restoreMs: null, summary, signed: base.signed, found, signedCookie: base.signedCookie, foundCookie } };
  }
  if (kind === "missing") {
    const summary = `Signed rule "${base.match}" was deleted from ${base.sw}`;
    const rules2 = rules.map((r) => (r.id === ruleId ? { ...r, found: null, foundCookie: null, status: "missing" as const } : r));
    return { rules: rules2, event: { t: now, kind, sw: base.sw, ruleId, detectMs, restoreMs: null, summary, signed: base.signed, found: null, signedCookie: base.signedCookie, foundCookie: null } };
  }
  const id = `${base.sw}-x${rules.length}`;
  const isShadow = kind === "shadow";
  const found = isShadow ? "output:99" : "output:controller";
  const foundCookie = fakeCookie(id);
  const summary = isShadow ? `An unknown higher-priority rule on ${base.sw} hides signed rule "${base.match}"` : `A rule the controller never installed appeared on ${base.sw}`;
  const rules2: SimRule[] = [
    ...rules.map((r) => (isShadow && r.id === ruleId ? { ...r, status: "shadow" as const } : r)),
    { id, sw: base.sw, table: base.table, priority: base.priority + 5, match: base.match, signed: null, found, signedCookie: null, foundCookie, status: kind },
  ];
  return { rules: rules2, event: { t: now, kind, sw: base.sw, ruleId: id, detectMs, restoreMs: null, summary, signed: null, found, signedCookie: null, foundCookie } };
}

/** Pure: restores the signed policy: removes unknown rules and puts signed rules back. */
export function repairAll(rules: SimRule[]): SimRule[] {
  return rules.filter((r) => r.signed !== null).map((r) => ({ ...r, found: r.signed, foundCookie: r.signedCookie, status: "ok" as const }));
}

interface DemoState {
  rules: SimRule[];
  events: SimEvent[];
  autoRepair: boolean;
  run: (kind: Kind, sw: string) => void;
  repair: () => void;
  reset: () => void;
  setAuto: (v: boolean) => void;
}
let seq = 0;
export const useDemo = create<DemoState>((set, get) => ({
  rules: freshRules(),
  events: [],
  autoRepair: false,
  setAuto: (v) => set({ autoRepair: v }),
  reset: () => set({ rules: freshRules(), events: [] }),
  repair: () => {
    const dt = Math.round(300 + Math.random() * 500);
    set((s) => ({ rules: repairAll(s.rules), events: s.events.map((e) => (e.restoreMs === null ? { ...e, restoreMs: dt } : e)) }));
  },
  run: (kind, sw) => {
    const target = get().rules.find((r) => r.sw === sw && r.signed !== null && r.status === "ok") ?? get().rules.find((r) => r.sw === sw && r.signed !== null)!;
    const { rules, event } = tamper(get().rules, kind, target.id, Date.now() / 1000);
    set((s) => ({ rules, events: [{ ...event, id: ++seq }, ...s.events].slice(0, 30) }));
    // tamper-and-revert reverts itself; with auto-repair on, the engine restores any other kind
    if (kind === "unattributed_change") setTimeout(() => get().repair(), 1400);
    else if (get().autoRepair) setTimeout(() => get().repair(), 900);
  },
}));
