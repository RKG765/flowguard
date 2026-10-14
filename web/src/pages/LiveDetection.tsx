import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Eye, Radio, ShieldCheck } from "lucide-react";
import { api, type Page } from "@/lib/api";
import { cn, fmtTime } from "@/lib/cn";
import { useLive } from "@/lib/live";
import type { Alert, AlertFull, EngineStatusFull } from "@/lib/types";
import { AlertExplain } from "@/components/alerts/AlertExplain";
import { RepairButton } from "@/components/rules/RepairButton";
import { Badge, Banner, CardTitle, DataSurface, EmptyState, GlassCard, SeverityBadge, Skeleton } from "@/components/ui/primitives";

const REPAIRABLE = new Set(["altered", "missing", "forged", "shadow"]);

/** Observation mode: shows, as it happens, how FlowGuard reacts to rule changes made outside the controller.
 *  The page itself never changes the switch, except through the admin-only, audited repair button. */
export function LiveDetection() {
  const [selected, setSelected] = useState<string | null>(null);
  const feed = useLive((s) => s.feed);
  const engine = useQuery({ queryKey: ["rules", "engine"], queryFn: () => api<EngineStatusFull>("/api/engine/status"), refetchInterval: 10000 });
  const recent = useQuery({ queryKey: ["alerts", "recent-live"], queryFn: () => api<Page<Alert>>("/api/alerts?limit=30"), refetchInterval: 15000 });
  const detail = useQuery({ queryKey: ["alerts", "detail", selected], queryFn: () => api<AlertFull>(`/api/alerts/${encodeURIComponent(selected!)}`), enabled: !!selected });
  const mode = engine.data?.status?.response_mode;
  const counters = engine.data?.status?.counters;
  const repairs = feed.filter((f) => f.type === "event" && f.kind.startsWith("repair_"));

  return (
    <div className="space-y-4">
      <Banner tone="info" icon={Eye}>
        Observation mode. This page shows FlowGuard's response to changes made to the lab switches from outside the controller, as they happen.
        It does not run anything against the switches.
      </Banner>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-3" aria-label="Engine response">
        <GlassCard>
          <CardTitle icon={ShieldCheck}>Remediation mode</CardTitle>
          {!engine.data ? <Skeleton className="h-6 w-40" /> : !engine.data.known ? (
            <p className="text-[13px] text-muted">The engine has not reported yet.</p>
          ) : mode === "alert_only" ? (
            <div className="space-y-1"><Badge tone="warn">Alert only</Badge><p className="text-[13px] text-muted">Detections are reported; repairs need an admin.</p></div>
          ) : (
            <div className="space-y-1"><Badge tone="ok">Automatic repair</Badge><p className="text-[13px] text-muted">Signed rules are restored and unsigned rules removed automatically (rate limited).</p></div>
          )}
        </GlassCard>
        <GlassCard>
          <CardTitle icon={Radio} aside={engine.data?.age_seconds !== undefined && engine.data?.age_seconds !== null ? <span className="text-[12px] text-muted">as of {Math.round(engine.data.age_seconds)} s ago</span> : undefined}>Engine counters</CardTitle>
          {counters ? (
            <dl className="grid grid-cols-2 gap-y-1 text-[13px]">
              <dt className="text-muted">Alerts</dt><dd className="tabular">{counters.alerts ?? 0}</dd>
              <dt className="text-muted">Restores</dt><dd className="tabular">{counters.restores ?? 0}</dd>
              <dt className="text-muted">Removals</dt><dd className="tabular">{counters.deletes ?? 0}</dd>
              <dt className="text-muted">Verification passes</dt><dd className="tabular">{counters.passes ?? 0}</dd>
            </dl>
          ) : <p className="text-[13px] text-muted">No counters reported yet.</p>}
        </GlassCard>
        <GlassCard>
          <CardTitle>Repairs requested from the dashboard</CardTitle>
          {!repairs.length ? <p className="text-[13px] text-muted">None in this session.</p> : (
            <ul className="space-y-1 text-[13px]">
              {repairs.slice(0, 6).map((r) => <li key={r.key} className="flex gap-2"><span className="mono text-muted">{fmtTime(r.t)}</span><span>{r.text}</span></li>)}
            </ul>
          )}
        </GlassCard>
      </section>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[420px_1fr]">
        <DataSurface className="p-0">
          <div className="border-b border-line px-4 py-2.5 text-[13px] font-semibold">Detections</div>
          {recent.isLoading ? (
            <div className="space-y-2 p-4">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-8 w-full" />)}</div>
          ) : !recent.data?.items.length ? (
            <EmptyState icon={Eye} title="Nothing detected yet">When a protected rule changes outside the controller, the detection appears here within moments.</EmptyState>
          ) : (
            <ul aria-label="Detections" aria-live="polite" className="max-h-[620px] overflow-y-auto">
              {recent.data.items.map((a) => (
                <li key={a.id}>
                  <button onClick={() => setSelected(a.id)} aria-current={a.id === selected ? "true" : undefined}
                          className={cn("flex w-full items-center gap-3 border-b border-line px-4 py-3 text-left hover:bg-surface-2", a.id === selected && "bg-primary/10")}>
                    <SeverityBadge severity={a.severity} />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[13.5px]">{a.kind.replace(/_/g, " ")}{a.priority !== null ? ` · priority ${a.priority}` : ""}</div>
                      <div className="text-[12px] text-muted">
                        {a.detect_latency_ms !== null ? `detected in ${a.detect_latency_ms.toFixed(1)} ms` : "detected"}
                        {a.time_to_restore_ms !== null ? ` · repaired in ${a.time_to_restore_ms.toFixed(1)} ms` : a.action === "none" ? " · not repaired" : ""}
                      </div>
                    </div>
                    <span className="text-[12px] text-muted">{fmtTime(a.t)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </DataSurface>
        <GlassCard>
          {!selected ? (
            <EmptyState icon={Eye} title="Select a detection">See what changed, how fast FlowGuard noticed it, and what it did.</EmptyState>
          ) : !detail.data ? <Skeleton className="h-64 w-full" /> : (
            <div className="space-y-4">
              <AlertExplain a={detail.data} />
              {detail.data.action === "none" && REPAIRABLE.has(detail.data.kind) && detail.data.dpid && detail.data.priority !== null && detail.data.details.match && (
                <RepairButton target={{ dpid: detail.data.dpid, table_id: detail.data.table_id ?? 0, priority: detail.data.priority, match: detail.data.details.match, status: detail.data.kind }} />
              )}
            </div>
          )}
        </GlassCard>
      </div>
    </div>
  );
}
