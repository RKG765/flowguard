import type { RuleRow } from "@/lib/types";
import { useQuery } from "@tanstack/react-query";
import { Activity, Brain, Clock, Radar, ShieldAlert, ShieldCheck, ShieldHalf } from "lucide-react";
import { api, type EngineEvent, type Incident, type Page, type ReportSummary, type RulesSummary } from "@/lib/api";
import { engineFresh, useLive } from "@/lib/live";
import { fmtAgo, fmtTime } from "@/lib/cn";
import { Kpi } from "@/components/ui/Kpi";
import { PortStrip, slotKey, useLitSlots } from "@/components/ui/Patch";
import { Badge, CardTitle, DataSurface, EmptyState, GlassCard, SEVERITY, SeverityBadge, Skeleton } from "@/components/ui/primitives";

const eventSeverity = (e: EngineEvent): string => {
  const d = e.data as Record<string, unknown>;
  if (typeof d.severity === "string" && d.severity in SEVERITY) return d.severity;
  return e.kind === "alert" || e.kind === "port_quarantined" ? "high" : "info";
};

/** Overview: every number comes from the core API; when there is no data the card says so (never a made-up value). */
export function Overview() {
  const rules = useQuery({ queryKey: ["rules", "summary"], queryFn: () => api<RulesSummary>("/api/rules/summary"), refetchInterval: 10000 });
  const report = useQuery({ queryKey: ["alerts", "summary"], queryFn: () => api<ReportSummary>("/api/reports/summary"), refetchInterval: 15000 });
  const incidents = useQuery({ queryKey: ["alerts", "incidents"], queryFn: () => api<Page<Incident>>("/api/incidents?limit=6"), refetchInterval: 15000 });
  const events = useQuery({ queryKey: ["alerts", "events"], queryFn: () => api<EngineEvent[]>("/api/events?limit=8"), refetchInterval: 15000 });
  const engine = useLive((s) => s.engine);
  const feed = useLive((s) => s.feed);
  const ports = useQuery({ queryKey: ["rules", "list", "ports"], queryFn: () => api<RuleRow[]>("/api/rules"), refetchInterval: 10000 });
  const l2 = useQuery({ queryKey: ["probes", "overview"], queryFn: () => api<{ available: boolean; items: unknown[] }>("/api/probes?limit=50"), refetchInterval: 10000 });
  const l3 = useQuery({ queryKey: ["ml", "overview"], queryFn: () => api<{ available: boolean; items: unknown[] }>("/api/ml/scores?limit=50"), refetchInterval: 10000 });
  const { lit } = useLitSlots();
  const l1Active = engineFresh(engine) && engine !== null && Object.values(engine.monitors_up).some(Boolean);

  return (
    <div className="space-y-5">
      <GlassCard aria-label="Patch panel">
        <CardTitle icon={ShieldHalf} aside={<span className="text-[12px] text-muted">{ports.data ? `${ports.data.filter((r) => r.status === "ok").length} of ${ports.data.length} ports verified` : ""}</span>}>
          Patch panel: one port per rule on the switch
        </CardTitle>
        {ports.data?.length ? <PortStrip ports={ports.data.map((r) => ({ status: r.status, label: `T${r.table_id} · P${r.priority}`, cookie: r.cookie, against: r.golden_cookie ?? undefined, lit: lit.has(slotKey(r.dpid, r.table_id, r.priority)) }))} /> : <p className="text-[13px] text-muted">Ports appear after the engine's first verification pass.</p>}
      </GlassCard>

      <section aria-label="Key figures" className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi label="Protected rules" value={rules.data ? rules.data.protected : null} icon={ShieldHalf} tone="info" loading={rules.isLoading}
             caption={rules.data?.as_of ? `as of ${fmtAgo(rules.data.as_of)}` : "waiting for the engine's first table snapshot"} />
        <Kpi label="Verified" value={rules.data?.verified_percent ?? null} format={(v) => `${v.toFixed(0)}%`} icon={ShieldCheck} tone="ok" loading={rules.isLoading}
             caption={rules.data ? `${rules.data.verified} of ${rules.data.protected} signed rules match` : undefined} />
        <Kpi label="Open incidents" value={report.data ? report.data.open_incidents : null} icon={ShieldAlert} tone={report.data?.open_incidents ? "danger" : "ok"} loading={report.isLoading}
             caption={report.data ? `${report.data.alerts_total} alerts recorded in total` : undefined} />
        <Kpi label="Mean detect time" value={report.data?.detect_latency_ms?.mean ?? null} format={(v) => v.toFixed(1)} unit="ms" icon={Clock} tone="info" loading={report.isLoading}
             empty="No alerts yet"
             caption={report.data?.detect_latency_ms ? `engine-side, ${report.data.detect_latency_ms.n} alerts (median ${report.data.detect_latency_ms.median} ms)` : "engine-side: monitor event to classification"} />
      </section>

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <GlassCard className="xl:col-span-2">
          <CardTitle icon={Activity}>Defense layers</CardTitle>
          <ul className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <li className="border-t border-line pt-3 md:border-l md:border-t-0 md:pl-4 md:pt-0 md:first:border-l-0 md:first:pl-0">
              {l1Active ? <Badge tone="ok" icon={ShieldCheck}>Active</Badge> : <Badge tone="warn">Not reporting</Badge>}
              <div className="mt-2 font-medium">L1 Authenticated rules</div>
              <p className="mt-2 text-[12.5px] text-muted">HMAC signatures in every rule cookie, checked on every change.</p>
              {engine && <p className="mono mt-2 text-muted">epoch {engine.epoch} · {engine.golden_rules} signed rules</p>}
            </li>
            <li className="border-t border-line pt-3 md:border-l md:border-t-0 md:pl-4 md:pt-0 md:first:border-l-0 md:first:pl-0">
              {l2.data?.available ? <Badge tone="ok" icon={Radar}>Active</Badge> : <Badge tone="warn" icon={Radar}>Waiting</Badge>}
              <div className="mt-2 font-medium">L2 Data-plane probes</div>
              <p className="mt-2 text-[12.5px] text-muted">Canary packets check that signed rules really forward as signed, which catches a switch that lies in its stats.</p>
              <p className="mono mt-2 text-muted">{l2.data?.available ? `${l2.data.items.length} recent results` : "no probe results yet"}</p>
            </li>
            <li className="border-t border-line pt-3 md:border-l md:border-t-0 md:pl-4 md:pt-0 md:first:border-l-0 md:first:pl-0">
              {l3.data?.available ? <Badge tone="ok" icon={Brain}>Active</Badge> : <Badge tone="warn" icon={Brain}>Waiting</Badge>}
              <div className="mt-2 font-medium">L3 Anomaly scoring</div>
              <p className="mt-2 text-[12.5px] text-muted">A baseline learned from normal rule churn scores each detected change, to catch a signed rule that behaves oddly.</p>
              <p className="mono mt-2 text-muted">{l3.data?.available ? `${l3.data.items.length} recent scores` : "scores appear on the next detection"}</p>
            </li>
          </ul>
          <p className="mt-4 text-[12px] text-muted">Each detection carries a fused risk decision (L1, L2 and L3 under the policy); open an alert to see it.</p>
        </GlassCard>

        <GlassCard>
          <CardTitle icon={Activity} aside={<span className="text-[12px] text-muted">live</span>}>
            Event feed
          </CardTitle>
          {feed.length === 0 && events.isLoading ? (
            <div className="space-y-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-5 w-full" />)}</div>
          ) : feed.length === 0 && !(events.data && events.data.length) ? (
            <EmptyState title="No events yet">Events appear here as soon as the engine reports them.</EmptyState>
          ) : (
            <ol className="space-y-2.5" aria-live="polite">
              {(feed.length ? feed.slice(0, 8) : (events.data ?? []).map((e) => ({ key: String(e.id), t: e.t, severity: eventSeverity(e), text: `${e.kind.replace(/_/g, " ")}${e.dpid ? ` (${e.dpid})` : ""}` }))).map((f) => (
                <li key={f.key} className="flex items-start gap-2.5 text-[13px]">
                  <span className="mono w-[92px] shrink-0 whitespace-nowrap text-muted">{fmtTime(f.t)}</span>
                  <SeverityBadge severity={f.severity} />
                  <span className="min-w-0 flex-1">{f.text}</span>
                </li>
              ))}
            </ol>
          )}
        </GlassCard>
      </section>

      <section aria-label="Recent incidents">
        <DataSurface className="p-0">
          <div className="flex items-center justify-between border-b border-line px-5 py-3">
            <h2 className="label !text-[13px] !text-fg">Recent incidents</h2>
            {incidents.data && <span className="text-[12px] text-muted">{incidents.data.total} total</span>}
          </div>
          {incidents.isLoading ? (
            <div className="space-y-2 p-5">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-6 w-full" />)}</div>
          ) : incidents.isError ? (
            <EmptyState icon={ShieldAlert} title="Could not load incidents">Check that the FlowGuard core is running.</EmptyState>
          ) : !incidents.data?.items.length ? (
            <EmptyState icon={ShieldCheck} title="No incidents">Nothing has been tampered with since FlowGuard started recording.</EmptyState>
          ) : (
            <table className="w-full text-left text-[13px]">
              <thead className="text-[11px] uppercase tracking-wide text-muted">
                <tr>
                  <th scope="col" className="px-5 py-2 font-medium">Severity</th>
                  <th scope="col" className="px-3 py-2 font-medium">Title</th>
                  <th scope="col" className="px-3 py-2 font-medium">Switch</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">Alerts</th>
                  <th scope="col" className="px-3 py-2 font-medium">Status</th>
                  <th scope="col" className="px-5 py-2 text-right font-medium">Updated</th>
                </tr>
              </thead>
              <tbody>
                {incidents.data.items.map((i) => (
                  <tr key={i.id} className="border-t border-line hover:bg-surface-2">
                    <td className="px-5 py-2.5"><SeverityBadge severity={i.severity} /></td>
                    <td className="px-3 py-2.5">{i.title}</td>
                    <td className="mono px-3 py-2.5 text-muted">{i.dpid ?? "—"}</td>
                    <td className="tabular px-3 py-2.5 text-right">{i.alert_count}</td>
                    <td className="px-3 py-2.5 capitalize">{i.status}</td>
                    <td className="px-5 py-2.5 text-right text-muted">{fmtAgo(i.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </DataSurface>
      </section>
      <p className="text-[12px] text-muted">Values come from the FlowGuard engine through the core API; nothing on this page is simulated.</p>
    </div>
  );
}
