import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Brain, Download, FileBarChart2, KeyRound, Radar, ScrollText, Settings as SettingsIcon, ShieldCheck, ShieldAlert, SlidersHorizontal } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError, type Page, type ReportSummary } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtAgo, fmtTime } from "@/lib/cn";
import { Badge, Banner, Button, CardTitle, DataSurface, EmptyState, Field, GlassCard, Skeleton } from "@/components/ui/primitives";
import { Kpi } from "@/components/ui/Kpi";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ReplayCard } from "./Replay";

const useRole = () => useAuth((s) => s.user)?.role ?? "viewer";
const err = (e: unknown) => (e instanceof ApiError ? e.detail : "Could not reach the core.");
const SEL = "h-9 rounded-[3px] border border-line bg-surface px-2 text-sm text-fg";

function Th({ children, right }: { children: ReactNode; right?: boolean }) {
  return <th scope="col" className={`label px-3 py-2 ${right ? "text-right" : ""}`}>{children}</th>;
}

/* ---- Policy (versioned; the core stores it, the Phase 5 risk engine will enforce it) ----------------------------- */
interface Policy {
  dry_run: boolean;
  response_mode: "restore" | "alert_only";
  critical_tables: number[];
  weights: { l1: number; l2: number; l3: number };
  thresholds: { alert: number; restore: number; quarantine: number };
  actions: Record<"critical" | "high" | "medium" | "low", string>;
}
interface PolicyDoc { version: number; updated_at: number; updated_by: string | null; enforced: boolean; enforced_fields?: string[]; policy: Policy }
const ACTIONS = ["restore_and_alert", "quarantine_port", "alert_only", "none"];

interface Quarantined { dpid: string; port: number; t: number }

/** Ports the engine cut because the policy asked for quarantine_port; an admin can release them. */
function QuarantineCard({ admin }: { admin: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["quarantine"], queryFn: () => api<{ items: Quarantined[] }>("/api/quarantine"), refetchInterval: 5000 });
  const release = useMutation({
    mutationFn: (i: Quarantined) => api("/api/quarantine/release", { method: "POST", body: { dpid: i.dpid, port: i.port } }),
    onSuccess: () => { toast.success("Release requested; the engine lifts the quarantine within a second"); void qc.invalidateQueries({ queryKey: ["quarantine"] }); },
    onError: (e) => toast.error(err(e)),
  });
  const items = q.data?.items ?? [];
  return (
    <GlassCard>
      <CardTitle icon={ShieldAlert} aside={<Badge tone={items.length ? "danger" : "ok"}>{items.length} quarantined</Badge>}>Quarantined ports</CardTitle>
      {!items.length ? (
        <p className="text-[13px] text-muted">No port is quarantined. A port is cut only when the policy action is quarantine_port, dry run is off, and the finding names a port.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((i) => (
            <li key={`${i.dpid}-${i.port}`} className="flex items-center gap-3 rounded-[3px] border border-line p-2.5 text-[13px]">
              <span className="mono">{i.dpid}</span><span>port <strong>{i.port}</strong></span>
              <span className="text-muted">since {fmtAgo(i.t)}</span>
              <Button size="sm" variant="secondary" className="ml-auto" disabled={!admin} loading={release.isPending} onClick={() => release.mutate(i)}>Release</Button>
            </li>
          ))}
        </ul>
      )}
    </GlassCard>
  );
}

export function PolicyPage() {
  const qc = useQueryClient();
  const admin = useRole() === "admin";
  const doc = useQuery({ queryKey: ["policy"], queryFn: () => api<PolicyDoc>("/api/policies") });
  const hist = useQuery({ queryKey: ["policy", "history"], queryFn: () => api<{ version: number; t: number; username: string | null }[]>("/api/policies/history"), retry: false });
  const [draft, setDraft] = useState<Policy | null>(null);
  const p = draft ?? doc.data?.policy;
  const save = useMutation({
    mutationFn: () => api<PolicyDoc>("/api/policies", { method: "PUT", body: draft }),
    onSuccess: () => { toast.success("Policy saved as a new version"); setDraft(null); void qc.invalidateQueries({ queryKey: ["policy"] }); },
    onError: (e) => toast.error(err(e)),
  });
  if (doc.isLoading || !p) return <Skeleton className="h-64 w-full" />;
  const set = (patch: Partial<Policy>) => setDraft({ ...p, ...patch });
  const num = (v: string) => Math.min(1, Math.max(0, Number(v) || 0));
  return (
    <div className="space-y-5">
      <Banner tone={doc.data!.enforced ? "ok" : "warn"}>
        {doc.data!.enforced ? `The engine enforces: ${(doc.data!.enforced_fields ?? []).join(", ").replace(/_/g, " ")}. Response mode and critical tables still come from the engine config file. ML alone can never repair a rule. Changes are audited.` : "This policy is stored and versioned, but not enforced."}
      </Banner>
      <GlassCard>
        <CardTitle icon={SlidersHorizontal} aside={<Badge tone="info">v{doc.data!.version}{doc.data!.updated_by ? ` by ${doc.data!.updated_by}` : ""}</Badge>}>Policy</CardTitle>
        <fieldset disabled={!admin} className="grid grid-cols-1 gap-5 md:grid-cols-2">
          <label className="flex items-center gap-2 text-[13.5px]"><input type="checkbox" checked={p.dry_run} onChange={(e) => set({ dry_run: e.target.checked })} className="h-4 w-4" /> Dry run (record what would happen, change nothing)</label>
          <label className="text-[13px]">Response mode<select className={`${SEL} mt-1 block`} value={p.response_mode} onChange={(e) => set({ response_mode: e.target.value as Policy["response_mode"] })}><option value="restore">restore</option><option value="alert_only">alert only</option></select></label>
          <Field label="Critical tables (comma separated)" value={p.critical_tables.join(",")} onChange={(e) => set({ critical_tables: e.target.value.split(",").map((x) => Number(x.trim())).filter((x) => Number.isInteger(x)) })} />
          <div className="grid grid-cols-3 gap-3">
            {(["l1", "l2", "l3"] as const).map((k) => <Field key={k} label={`Weight ${k.toUpperCase()}`} type="number" step="0.1" min="0" max="1" value={p.weights[k]} onChange={(e) => set({ weights: { ...p.weights, [k]: num(e.target.value) } })} />)}
          </div>
          <div className="grid grid-cols-3 gap-3 md:col-span-2">
            {(["alert", "restore", "quarantine"] as const).map((k) => <Field key={k} label={`Threshold: ${k}`} type="number" step="0.05" min="0" max="1" value={p.thresholds[k]} onChange={(e) => set({ thresholds: { ...p.thresholds, [k]: num(e.target.value) } })} />)}
          </div>
          <div className="grid grid-cols-2 gap-3 md:col-span-2 md:grid-cols-4">
            {(["critical", "high", "medium", "low"] as const).map((k) => (
              <label key={k} className="text-[13px] capitalize">{k} severity<select className={`${SEL} mt-1 block w-full`} value={p.actions[k]} onChange={(e) => set({ actions: { ...p.actions, [k]: e.target.value } })}>{ACTIONS.map((a) => <option key={a}>{a}</option>)}</select></label>
            ))}
          </div>
        </fieldset>
        <div className="mt-4 flex items-center gap-2">
          <Button onClick={() => save.mutate()} disabled={!admin || !draft} loading={save.isPending}>Save new version</Button>
          <Button variant="secondary" onClick={() => setDraft(null)} disabled={!draft}>Discard</Button>
          {!admin && <span className="text-[12.5px] text-muted">Only an admin can change the policy.</span>}
        </div>
      </GlassCard>
      <QuarantineCard admin={admin} />
      <DataSurface className="p-0">
        <div className="border-b border-line px-5 py-3"><h2 className="label !text-fg">Version history</h2></div>
        {hist.data?.length ? (
          <table className="w-full text-left text-[13px]"><thead><tr><Th>Version</Th><Th>When</Th><Th>By</Th></tr></thead>
            <tbody>{hist.data.map((h) => <tr key={h.version} className="border-t border-line"><td className="tabular px-3 py-2">v{h.version}</td><td className="px-3 py-2">{fmtTime(h.t)} · {fmtAgo(h.t)}</td><td className="px-3 py-2">{h.username ?? "system"}</td></tr>)}</tbody></table>
        ) : <EmptyState title="History needs analyst access" />}
      </DataSurface>
    </div>
  );
}

/* ---- Reports ----------------------------------------------------------------------------------------------------- */
export function ReportsPage() {
  const rep = useQuery({ queryKey: ["alerts", "report"], queryFn: () => api<ReportSummary & { alerts_by_severity?: Record<string, number>; note?: string }>("/api/reports/summary"), refetchInterval: 15000 });
  const role = useRole();
  const d = rep.data;
  const bars = Object.entries(d?.alerts_by_kind ?? {});
  const max = Math.max(1, ...bars.map(([, n]) => n));
  return (
    <div className="space-y-5">
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi label="Alerts" value={d ? d.alerts_total : null} icon={ShieldAlert} tone="danger" loading={rep.isLoading} />
        <Kpi label="Open incidents" value={d ? d.open_incidents : null} icon={ShieldCheck} tone={d?.open_incidents ? "warn" : "ok"} loading={rep.isLoading} />
        <Kpi label="Median detect" value={d?.detect_latency_ms?.median ?? null} unit="ms" format={(v) => v.toFixed(1)} icon={FileBarChart2} tone="info" empty="No alerts yet" />
        <Kpi label="Median restore" value={d?.time_to_restore_ms?.median ?? null} unit="ms" format={(v) => v.toFixed(0)} icon={FileBarChart2} tone="info" empty="No restores yet" />
      </section>
      <GlassCard>
        <CardTitle icon={FileBarChart2} aside={role !== "viewer" ? <span className="flex gap-2"><a href="/api/reports/alerts.csv" download><Button variant="secondary" size="sm"><Download aria-hidden className="h-4 w-4" /> Alerts CSV</Button></a><a href="/api/reports/summary.pdf" download><Button variant="secondary" size="sm"><Download aria-hidden className="h-4 w-4" /> Report PDF</Button></a></span> : <span className="text-[12px] text-muted">CSV needs analyst access</span>}>Alerts by kind</CardTitle>
        {bars.length ? (
          <ul className="space-y-2">{bars.map(([k, n]) => (
            <li key={k} className="grid grid-cols-[160px_1fr_40px] items-center gap-3 text-[13px]">
              <span className="capitalize">{k.replace(/_/g, " ")}</span>
              <span className="h-4 bg-surface-2"><span className="block h-4 bg-primary-strong" style={{ width: `${(n / max) * 100}%` }} /></span>
              <span className="tabular text-right">{n}</span>
            </li>))}</ul>
        ) : <EmptyState icon={ShieldCheck} title="No alerts recorded">Reports are computed only from stored alerts; nothing is invented.</EmptyState>}
        {d?.note && <p className="mt-3 text-[12px] text-muted">{d.note}</p>}
      </GlassCard>
      <ReplayCard />
    </div>
  );
}

/* ---- Audit log ---------------------------------------------------------------------------------------------------- */
interface AuditRow { id: number; t: number; username: string | null; role: string | null; action: string; target: string | null; result: string; hash: string | null }
export function AuditPage() {
  const role = useRole();
  const log = useQuery({ queryKey: ["audit"], queryFn: () => api<Page<AuditRow>>("/api/audit?limit=200"), retry: false, refetchInterval: 20000 });
  const chain = useQuery({ queryKey: ["audit", "verify"], queryFn: () => api<{ ok: boolean; first_bad_id: number | null; rows_checked: number }>("/api/audit/verify"), enabled: role === "admin", retry: false });
  if (role === "viewer") return <GlassCard><EmptyState icon={ScrollText} title="Analyst or admin role required" /></GlassCard>;
  return (
    <div className="space-y-5">
      {chain.data && <Banner tone={chain.data.ok ? "ok" : "danger"}>{chain.data.ok ? `Hash chain intact (${chain.data.rows_checked} rows checked).` : `Hash chain BROKEN at row ${chain.data.first_bad_id}: the log was changed after it was written.`}</Banner>}
      <DataSurface className="p-0">
        <div className="flex items-center justify-between border-b border-line px-5 py-3"><h2 className="label !text-fg">Audit log</h2>{log.data && <span className="text-[12px] text-muted">{log.data.total} entries</span>}</div>
        {log.isLoading ? <div className="p-5"><Skeleton className="h-24 w-full" /></div> : !log.data?.items.length ? <EmptyState icon={ScrollText} title="No audit entries yet" /> : (
          <table className="w-full text-left text-[13px]"><thead><tr><Th>Time</Th><Th>User</Th><Th>Action</Th><Th>Target</Th><Th>Result</Th><Th>Hash</Th></tr></thead>
            <tbody>{log.data.items.map((e) => (
              <tr key={e.id} className="border-t border-line hover:bg-surface-2">
                <td className="mono px-3 py-2 text-muted">{fmtTime(e.t)}</td><td className="px-3 py-2">{e.username ?? "-"} <span className="text-muted">{e.role}</span></td>
                <td className="px-3 py-2">{e.action}</td><td className="mono px-3 py-2 text-muted">{e.target ?? "-"}</td>
                <td className="px-3 py-2"><Badge tone={e.result === "ok" ? "ok" : "warn"}>{e.result}</Badge></td><td className="mono px-3 py-2 text-muted">{(e.hash ?? "").slice(0, 12)}</td>
              </tr>))}</tbody></table>
        )}
      </DataSurface>
    </div>
  );
}

/* ---- Settings: users and key rotation ------------------------------------------------------------------------------ */
interface UserRow { id: number; username: string; role: string; disabled: boolean; last_login: number | null }
export function SettingsPage() {
  const qc = useQueryClient();
  const role = useRole();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<UserRow[]>("/api/users"), enabled: role === "admin", retry: false });
  const [f, setF] = useState({ username: "", password: "", role: "viewer" });
  const [confirm, setConfirm] = useState(false);
  const create = useMutation({
    mutationFn: () => api("/api/users", { method: "POST", body: f }),
    onSuccess: () => { toast.success("User created"); setF({ username: "", password: "", role: "viewer" }); void qc.invalidateQueries({ queryKey: ["users"] }); },
    onError: (e) => toast.error(err(e)),
  });
  const toggle = useMutation({
    mutationFn: (u: UserRow) => api(`/api/users/${u.id}`, { method: "PATCH", body: { disabled: !u.disabled } }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["users"] }),
    onError: (e) => toast.error(err(e)),
  });
  const rotate = useMutation({
    mutationFn: () => api<{ note: string }>("/api/engine/rotate-key", { method: "POST" }),
    onSuccess: (r) => { toast.success(r.note); setConfirm(false); },
    onError: (e) => { toast.error(err(e)); setConfirm(false); },
  });
  if (role !== "admin") return <GlassCard><EmptyState icon={SettingsIcon} title="Admin role required">Users and key rotation are admin-only.</EmptyState></GlassCard>;
  return (
    <div className="space-y-5">
      <section className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <DataSurface className="p-0 xl:col-span-2">
          <div className="border-b border-line px-5 py-3"><h2 className="label !text-fg">Users</h2></div>
          <table className="w-full text-left text-[13px]"><thead><tr><Th>User</Th><Th>Role</Th><Th>Last login</Th><Th right>Access</Th></tr></thead>
            <tbody>{(users.data ?? []).map((u) => (
              <tr key={u.id} className="border-t border-line"><td className="px-3 py-2">{u.username}</td><td className="px-3 py-2 capitalize">{u.role}</td><td className="px-3 py-2 text-muted">{u.last_login ? fmtAgo(u.last_login) : "never"}</td>
                <td className="px-3 py-2 text-right"><Button size="sm" variant="secondary" onClick={() => toggle.mutate(u)}>{u.disabled ? "Enable" : "Disable"}</Button></td></tr>))}</tbody></table>
        </DataSurface>
        <GlassCard>
          <CardTitle icon={SettingsIcon}>Add user</CardTitle>
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
            <Field label="Username" value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} autoComplete="off" />
            <Field label="Password" type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} autoComplete="new-password" hint="At least 8 characters" />
            <label className="block text-[13px]">Role<select className={`${SEL} mt-1 block w-full`} value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}><option>viewer</option><option>analyst</option><option>admin</option></select></label>
            <Button type="submit" className="w-full" loading={create.isPending} disabled={!f.username || !f.password}>Create user</Button>
          </form>
        </GlassCard>
      </section>
      <GlassCard>
        <CardTitle icon={KeyRound}>Signing key</CardTitle>
        <p className="mb-3 text-[13.5px] text-muted">Starts a new key epoch: every protected rule is re-signed. No alerts are expected.</p>
        <Button variant="secondary" onClick={() => setConfirm(true)}>Rotate HMAC key</Button>
      </GlassCard>
      <ConfirmDialog open={confirm} onOpenChange={setConfirm} title="Rotate the signing key?" confirmLabel="Rotate key" onConfirm={() => rotate.mutate()} busy={rotate.isPending}>
        <p>The engine re-signs every protected rule under a new key. This is recorded in the audit log.</p>
      </ConfirmDialog>
    </div>
  );
}

/* ---- Probes (L2) and ML (L3): live API data, honest when the layer is not running -------------------------------- */
interface LayerDoc { layer: string; available: boolean; note: string; items: { id: number; t: number; dpid: string | null; score?: number; data: Record<string, unknown> }[] }
function Layer({ path, title, icon, simNote }: { path: string; title: string; icon: typeof Radar; simNote: string }) {
  const q = useQuery({ queryKey: [path], queryFn: () => api<LayerDoc>(path), refetchInterval: 10000 });
  return (
    <div className="space-y-5">
      <Banner tone={q.data?.available ? "ok" : "info"}>
        {q.data?.available ? `${title} is running inside the engine.` : `${q.data?.note ?? "Checking"}. `}
        {!q.data?.available && <>{simNote} <Link to="/demo" className="underline">Open the Demo Lab</Link>.</>}
      </Banner>
      <DataSurface className="p-0">
        <div className="border-b border-line px-5 py-3"><h2 className="label !text-fg">{title} results from the engine</h2></div>
        {!q.data?.items.length ? <EmptyState icon={icon} title={`No ${title} results recorded`} /> : (
          <table className="w-full text-left text-[13px]"><thead><tr><Th>Time</Th><Th>Switch</Th>{q.data.items[0]?.score !== undefined && <Th>Score</Th>}<Th>Data</Th></tr></thead>
            <tbody>{q.data.items.map((r) => <tr key={r.id} className="border-t border-line"><td className="mono px-3 py-2 text-muted">{fmtTime(r.t)}</td><td className="mono px-3 py-2">{r.dpid ?? "-"}</td>{r.score !== undefined && <td className="tabular px-3 py-2">{r.score.toFixed(2)}</td>}<td className="mono px-3 py-2 text-muted">{JSON.stringify(r.data).slice(0, 120)}</td></tr>)}</tbody></table>
        )}
      </DataSurface>
    </div>
  );
}
export const ProbesPage = () => <Layer path="/api/probes" title="L2 probe" icon={Radar} simNote="The Demo Lab shows simulated canary probes failing when forwarding is tampered." />;
export const MlPage = () => <Layer path="/api/ml/scores" title="L3 ML score" icon={Brain} simNote="The Demo Lab shows a simulated anomaly score and the fused risk." />;
