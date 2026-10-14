import { useQuery } from "@tanstack/react-query";
import { Activity, Brain, Clock, Radar, ShieldAlert, ShieldCheck, ShieldHalf } from "lucide-react";
import { api, type EngineEvent, type Incident, type Page, type ReportSummary, type RulesSummary } from "@/lib/api";
import { engineFresh, useLive } from "@/lib/live";
import { fmtAgo, fmtTime } from "@/lib/cn";
import { Kpi } from "@/components/ui/Kpi";
import { Badge, CardTitle, DataSurface, EmptyState, GlassCard, SeverityBadge, Skeleton } from "@/components/ui/primitives";

/** Overview: every number comes from the core API; when there is no data the card says so (never a made-up value). */
export function Overview() {
  const rules = useQuery({ queryKey: ["rules", "summary"], queryFn: () => api<RulesSummary>("/api/rules/summary"), refetchInterval: 10000 });
  const report = useQuery({ queryKey: ["alerts", "summary"], queryFn: () => api<ReportSummary>("/api/reports/summary"), refetchInterval: 15000 });
  const incidents = useQuery({ queryKey: ["alerts", "incidents"], queryFn: () => api<Page<Incident>>("/api/incidents?limit=6"), refetchInterval: 15000 });
  const events = useQuery({ queryKey: ["alerts", "events"], queryFn: () => api<EngineEvent[]>("/api/events?limit=8"), refetchInterval: 15000 });
  const engine = useLive((s) => s.engine);
  const feed = useLive((s) => s.feed);
  const l1Active = engineFresh(engine) && engine !== null && Object.values(engine.monitors_up).some(Boolean);

  return (
    <div className="space-y-5">
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
            <li className="rounded-[14px] border border-line bg-surface/60 p-4">
              {l1Active ? <Badge tone="ok" icon={ShieldCheck}>Active</Badge> : <Badge tone="warn">Not reporting</Badge>}
              <div className="mt-2 font-medium">L1 Authenticated rules</div>
              <p className="mt-2 text-[12.5px] text-muted">HMAC signatures in every rule cookie, checked on every change.</p>
              {engine && <p className="mono mt-2 text-muted">epoch {engine.epoch} · {engine.golden_rules} signed rules</p>}
            </li>
            <li className="rounded-[14px] border border-line bg-surface/60 p-4">
              <Badge tone="muted" icon={Radar}>Planned</Badge>
              <div className="mt-2 font-medium">L2 Data-plane probes</div>
              <p className="mt-2 text-[12.5px] text-muted">Canary packets that catch a switch lying in its stats. Arrives in Phase 5.</p>
            </li>
            <li className="rounded-[14px] border border-line bg-surface/60 p-4">
              <Badge tone="muted" icon={Brain}>Planned</Badge>
              <div className="mt-2 font-medium">L3 ML scoring</div>
              <p className="mt-2 text-[12.5px] text-muted">Anomaly scoring for signed-but-malicious rules. Arrives in Phase 5.</p>
            </li>
          </ul>
          <p className="mt-4 text-[12px] text-muted">The risk trend chart appears with the risk engine (Phase 5); no risk scores exist yet.</p>
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
              {(feed.length ? feed.slice(0, 8) : (events.data ?? []).map((e) => ({ key: String(e.id), t: e.t, severity: "info", text: `${e.kind.replace(/_/g, " ")}${e.dpid ? ` (${e.dpid})` : ""}` }))).map((f) => (
                <li key={f.key} className="flex items-start gap-2.5 text-[13px]">
                  <span className="mono w-[64px] shrink-0 text-muted">{fmtTime(f.t)}</span>
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
            <h2 className="text-[15px] font-semibold">Recent incidents</h2>
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
