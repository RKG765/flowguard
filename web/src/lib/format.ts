/** Human-readable rendering of normalized rules (engine/canonical.py form) for the dashboard. */

export type Match = Record<string, unknown>;
export interface Action { type: string; [k: string]: unknown }
export interface Instruction { type: string; actions?: Action[]; [k: string]: unknown }

const PORTS: Record<number, string> = {
  0xfffffff8: "IN_PORT", 0xfffffff9: "TABLE", 0xfffffffa: "NORMAL", 0xfffffffb: "FLOOD",
  0xfffffffc: "ALL", 0xfffffffd: "CONTROLLER", 0xfffffffe: "LOCAL", 0xffffffff: "ANY",
};
const HEX_FIELDS = new Set(["eth_type", "metadata", "tunnel_id"]);
const LABELS: Record<string, string> = { eth_type: "eth_type", ip_proto: "ip_proto" };

export function fmtValue(field: string, v: unknown): string {
  if (Array.isArray(v)) return `${fmtValue(field, v[0])}/${fmtValue(field, v[1])}`;
  if (typeof v === "number" && HEX_FIELDS.has(field)) return `0x${v.toString(16)}`;
  return String(v);
}

export function formatMatch(m: Match | null | undefined): string {
  const keys = Object.keys(m ?? {});
  if (!keys.length) return "any packet";
  return keys.map((k) => `${LABELS[k] ?? k}=${fmtValue(k, (m as Match)[k])}`).join(", ");
}

export function formatAction(a: Action): string {
  switch (a.type) {
    case "output": {
      const p = Number(a.port);
      return `output:${PORTS[p] ?? p}`;
    }
    case "set_field":
      return `set ${String(a.field)}=${fmtValue(String(a.field), a.value)}`;
    case "group":
      return `group:${String(a.group_id)}`;
    case "set_queue":
      return `queue:${String(a.queue_id)}`;
    case "push_vlan":
      return `push_vlan:0x${Number(a.ethertype).toString(16)}`;
    case "raw":
      return `${String(a.class)}(${JSON.stringify(a.params)})`;
    default:
      return a.type;
  }
}

/** One line per instruction, in OpenFlow execution order (the engine already sorted them). Empty = drop. */
export function formatInstructions(ins: Instruction[] | null | undefined): string[] {
  if (!ins || ins.length === 0) return ["drop"];
  return ins.map((i) => {
    if (i.type === "goto_table") return `goto_table:${String(i.table_id)}`;
    if (i.type === "apply_actions" || i.type === "write_actions") {
      const acts = (i.actions ?? []).map(formatAction);
      return `${i.type === "apply_actions" ? "apply" : "write"}: ${acts.length ? acts.join(", ") : "drop"}`;
    }
    if (i.type === "clear_actions") return "clear_actions";
    if (i.type === "write_metadata") return `write_metadata:${String(i.metadata)}/${String(i.mask)}`;
    if (i.type === "meter") return `meter:${String(i.meter_id)}`;
    return i.type;
  });
}

/** Line-level comparison of signed vs observed instructions for the diff view. */
export function diffLines(signed: string[], observed: string[]): { line: string; side: "both" | "signed" | "observed" }[] {
  const out: { line: string; side: "both" | "signed" | "observed" }[] = [];
  const obs = new Set(observed);
  const sig = new Set(signed);
  for (const l of signed) out.push({ line: l, side: obs.has(l) ? "both" : "signed" });
  for (const l of observed) if (!sig.has(l)) out.push({ line: l, side: "observed" });
  return out;
}

/** Spreadsheet-safe CSV cell (formula injection guard, quoting). */
export function csvCell(v: unknown): string {
  let s = v === null || v === undefined ? "" : String(v);
  if (/^[=+\-@\t\r]/.test(s)) s = `'${s}`;
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export const shortCookie = (c: string | null | undefined): string => (c ? `0x${c.replace(/^0+(?=.)/, "")}` : "—");
