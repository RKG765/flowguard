import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, CircleOff, Clock, Layers, X, type LucideIcon } from "lucide-react";
import { toast } from "sonner";
import { api, type Page } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Alert } from "@/lib/types";
import { cn } from "@/lib/cn";
import { Button, RULE_STATUS } from "./primitives";

/* Signature move of the "Patch Panel" world: a rule's HMAC cookie is drawn as an 8-band wire-code stripe (one band per
   byte), and the whole policy as a panel of numbered ports, one per rule on the switch. The stripe is a visual fingerprint for
   comparing signed vs found at a glance; the exact hex always sits beside it. A port or row stays lit after a change until
   an operator acknowledges the alert, even when the engine has already repaired the rule. */

/** Standard wire-colour-code inks (blue, orange, green, brown, slate, red, violet, yellow, white, rose, aqua, black). */
const WIRE = ["#3b82c4", "#f08a24", "#3fae5a", "#8a5a3c", "#7b8794", "#d6453d", "#8e63c9", "#e6c229", "#ece8dc", "#e57fa3", "#34b5b0", "#2b2f36"];

/** Hex cookie -> 8 band indices (one per byte). A zero cookie means "not signed by the controller": no stripe. */
export function cookieBands(cookie: string | null | undefined): number[] | null {
  if (!cookie) return null;
  const hex = cookie.replace(/^0x/i, "").replace(/[^0-9a-f]/gi, "").padStart(16, "0").slice(-16);
  if (/^0+$/.test(hex)) return null;
  return Array.from({ length: 8 }, (_, i) => parseInt(hex.slice(i * 2, i * 2 + 2), 16) % WIRE.length);
}

export function TagStripe({ cookie, against, className }: { cookie: string | null | undefined; against?: string | null; className?: string }) {
  const bands = cookieBands(cookie);
  const ref = against === undefined ? null : cookieBands(against);
  if (!bands) return <span className="mono text-muted">no tag</span>;
  return (
    <span className={cn("inline-flex h-4 items-stretch overflow-hidden rounded-[2px] border border-line", className)} role="img" aria-label={`Tag fingerprint ${cookie}`}>
      {bands.map((b, i) => {
        const differs = ref !== null && ref[i] !== b;
        return (
          <span key={i} className="relative w-[7px]" style={{ background: WIRE[b] }}>
            {differs && <span aria-hidden className="absolute inset-x-0 bottom-0 h-[5px] bg-[repeating-linear-gradient(135deg,#000_0_2px,#fff_2px_4px)]" />}
          </span>
        );
      })}
    </span>
  );
}

const PORT_ICON: Record<string, LucideIcon> = { ok: Check, altered: AlertTriangle, forged: X, shadow: Layers, missing: CircleOff, pending: Clock };
const PORT_TONE: Record<string, string> = {
  ok: "border-ok/60 bg-ok/10 text-ok",
  altered: "border-danger bg-danger/15 text-danger",
  forged: "border-danger bg-danger/15 text-danger",
  shadow: "border-danger bg-danger/15 text-danger",
  missing: "border-warn bg-warn/15 text-warn",
  pending: "border-info/60 bg-info/10 text-info",
};

export interface Port {
  status: string;
  label: string;
  cookie?: string | null;
  against?: string | null;
  lit?: boolean;
}

/** One numbered tile per rule: index, status icon (never colour alone), rule label and the tag stripe. */
export function PortStrip({ ports, onPick }: { ports: Port[]; onPick?: (index: number) => void }) {
  return (
    <ol className="grid grid-cols-[repeat(auto-fit,minmax(104px,1fr))] gap-2" aria-label="Rules, one port each">
      {ports.map((p, i) => {
        const Icon = PORT_ICON[p.status] ?? Clock;
        const word = RULE_STATUS[p.status]?.label ?? p.status;
        return (
          <li key={i}>
            <button
              type="button"
              onClick={() => onPick?.(i)}
              title={`${p.label}: ${word}`}
              aria-label={`Rule ${i + 1}, ${p.label}: ${word}${p.lit ? ", changed and not acknowledged" : ""}`}
              className={cn("flex w-full flex-col gap-1.5 rounded-[3px] border p-2 text-left", PORT_TONE[p.status] ?? "border-line bg-surface-2 text-muted", p.lit && "row-lit")}
            >
              <span className="flex items-center justify-between font-mono text-[18px] font-semibold">
                <span>{String(i + 1).padStart(2, "0")}</span>
                <Icon aria-hidden className="h-5 w-5" />
              </span>
              <span className="truncate font-mono text-[11px] leading-none text-fg">{p.label}</span>
              <TagStripe cookie={p.cookie} against={p.against} className="h-3" />
            </button>
          </li>
        );
      })}
    </ol>
  );
}

export const slotKey = (dpid: string, table: number, priority: number) => `${dpid}|${table}|${priority}`;

/** Rule slots with an alert nobody has acknowledged yet: they stay lit even after the engine repaired the rule. */
export function useLitSlots(): { lit: Set<string>; alerts: Alert[] } {
  const q = useQuery({ queryKey: ["alerts", "lit"], queryFn: () => api<Page<Alert>>("/api/alerts?limit=200"), refetchInterval: 5000 });
  return useMemo(() => {
    const alerts = (q.data?.items ?? []).filter((a) => a.status !== "acknowledged" && a.dpid && a.table_id !== null && a.priority !== null);
    return { lit: new Set(alerts.map((a) => slotKey(a.dpid!, a.table_id!, a.priority!))), alerts };
  }, [q.data]);
}

/** Acknowledge every open alert of one rule slot (analyst or admin); the slot stops being lit. */
export function AckButton({ dpid, table, priority }: { dpid: string; table: number; priority: number }) {
  const qc = useQueryClient();
  const role = useAuth((s) => s.user)?.role ?? "viewer";
  const { alerts } = useLitSlots();
  const mine = alerts.filter((a) => slotKey(a.dpid!, a.table_id!, a.priority!) === slotKey(dpid, table, priority));
  const ack = useMutation({
    mutationFn: () => Promise.all(mine.map((a) => api(`/api/alerts/${encodeURIComponent(a.id)}/ack`, { method: "POST" }))),
    onSuccess: () => { toast.success("Acknowledged"); void qc.invalidateQueries({ queryKey: ["alerts"] }); },
    onError: () => toast.error("Could not acknowledge"),
  });
  if (!mine.length) return null;
  return (
    <Button variant="secondary" size="sm" onClick={() => ack.mutate()} loading={ack.isPending} disabled={role === "viewer"}>
      Acknowledge {mine.length} alert{mine.length > 1 ? "s" : ""}
    </Button>
  );
}
