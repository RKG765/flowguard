import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Bell, CheckCheck, FolderOpen } from "lucide-react";
import { api, ApiError, type Incident, type Page } from "@/lib/api";
import { hasRole, useAuth } from "@/lib/auth";
import { useLive } from "@/lib/live";
import { cn, fmtAgo, fmtTime } from "@/lib/cn";
import type { Alert, AlertFull, IncidentDetail } from "@/lib/types";
import { AlertExplain } from "@/components/alerts/AlertExplain";
import { Badge, Button, CardTitle, DataSurface, EmptyState, Field, GlassCard, SeverityBadge, Skeleton } from "@/components/ui/primitives";

const SEVERITIES = ["", "high", "medium", "low"];

function AlertsTab() {
  const [params, setParams] = useSearchParams();
  const [severity, setSeverity] = useState("");
  const selected = params.get("id");
  const user = useAuth((s) => s.user);
  const qc = useQueryClient();
  const list = useQuery({
    queryKey: ["alerts", "list", severity],
    queryFn: () => api<Page<Alert>>(`/api/alerts?limit=200${severity ? `&severity=${severity}` : ""}`),
    refetchInterval: 15000,
  });
  const detail = useQuery({ queryKey: ["alerts", "detail", selected], queryFn: () => api<AlertFull>(`/api/alerts/${encodeURIComponent(selected!)}`), enabled: !!selected });
  const ack = useMutation({
    mutationFn: (id: string) => api<Alert>(`/api/alerts/${encodeURIComponent(id)}/ack`, { method: "POST" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["alerts"] }),
    onError: (e) => toast.error(e instanceof ApiError ? e.detail : "Could not acknowledge"),
  });

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_520px]">
      <DataSurface className="p-0">
        <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
          <label className="flex items-center gap-2 text-[12px] text-muted">
            Severity
            <select value={severity} onChange={(e) => setSeverity(e.target.value)} className="h-8 rounded-[8px] border border-line bg-surface px-2 text-[13px] text-fg">
              {SEVERITIES.map((s) => <option key={s} value={s}>{s || "All"}</option>)}
            </select>
          </label>
          {list.data && <span className="text-[12px] text-muted">{list.data.total} alerts</span>}
        </div>
        {list.isLoading ? (
          <div className="space-y-2 p-4">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-8 w-full" />)}</div>
        ) : !list.data?.items.length ? (
          <EmptyState icon={Bell} title="No alerts">FlowGuard raises an alert when a protected rule is changed outside the controller.</EmptyState>
        ) : (
          <ul aria-label="Alerts" className="max-h-[640px] overflow-y-auto">
            {list.data.items.map((a) => (
              <li key={a.id}>
                <button onClick={() => setParams({ id: a.id })} aria-current={a.id === selected ? "true" : undefined}
                        className={cn("flex w-full items-start gap-3 border-b border-line px-4 py-3 text-left hover:bg-surface-2", a.id === selected && "bg-primary/10")}>
                  <SeverityBadge severity={a.severity} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[13.5px] font-medium">{a.kind.replace(/_/g, " ")}{a.priority !== null ? ` · priority ${a.priority}` : ""}</div>
                    <div className="truncate text-[12.5px] text-muted">{a.summary}</div>
                  </div>
                  <div className="shrink-0 text-right text-[12px] text-muted">
                    <div>{fmtTime(a.t)}</div>
                    <div>{a.status === "acknowledged" ? "acknowledged" : a.action ?? ""}</div>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </DataSurface>
      <GlassCard>
        {!selected ? (
          <EmptyState icon={Bell} title="Select an alert">Its explanation, timeline and the rule before the repair appear here.</EmptyState>
        ) : detail.isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : detail.isError || !detail.data ? (
          <EmptyState title="Alert not found" />
        ) : (
          <>
            <CardTitle aside={hasRole(user, "analyst") && detail.data.status !== "acknowledged" ? (
              <Button size="sm" variant="secondary" onClick={() => ack.mutate(detail.data!.id)} loading={ack.isPending}>
                <CheckCheck aria-hidden className="h-4 w-4" /> Acknowledge
              </Button>
            ) : detail.data.status === "acknowledged" ? <Badge tone="ok">Acknowledged by {detail.data.acknowledged_by}</Badge> : undefined}>
              Alert
            </CardTitle>
            <AlertExplain a={detail.data} />
          </>
        )}
      </GlassCard>
    </div>
  );
}

function IncidentPanel({ id }: { id: number }) {
  const user = useAuth((s) => s.user);
  const canEdit = hasRole(user, "analyst");
  const qc = useQueryClient();
  const inc = useQuery({ queryKey: ["alerts", "incident", id], queryFn: () => api<IncidentDetail>(`/api/incidents/${id}`) });
  const [note, setNote] = useState("");
  const [assignee, setAssignee] = useState("");
  useEffect(() => setAssignee(inc.data?.assignee ?? ""), [inc.data?.assignee]);
  const refresh = () => void qc.invalidateQueries({ queryKey: ["alerts"] });
  const patch = useMutation({
    mutationFn: (body: Record<string, unknown>) => api(`/api/incidents/${id}`, { method: "PATCH", body }),
    onSuccess: refresh,
    onError: (e) => toast.error(e instanceof ApiError ? e.detail : "Could not update the incident"),
  });
  const addNote = useMutation({
    mutationFn: (text: string) => api(`/api/incidents/${id}/notes`, { method: "POST", body: { text } }),
    onSuccess: () => {
      setNote("");
      refresh();
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.detail : "Could not add the note"),
  });
  if (inc.isLoading || !inc.data) return <Skeleton className="h-64 w-full" />;
  const i = inc.data;
  return (
    <div className="space-y-4">
      <CardTitle aside={<SeverityBadge severity={i.severity} />}>{i.title}</CardTitle>
      <dl className="grid grid-cols-[110px_1fr] gap-y-1.5 text-[13px]">
        <dt className="text-muted">Status</dt><dd className="capitalize">{i.status}</dd>
        <dt className="text-muted">Switch</dt><dd className="mono">{i.dpid ?? "—"}</dd>
        <dt className="text-muted">Opened</dt><dd>{fmtAgo(i.created_at)}</dd>
        <dt className="text-muted">Alerts</dt><dd className="tabular">{i.alert_count}</dd>
      </dl>
      {canEdit && (
        <div className="flex flex-wrap items-end gap-2">
          <form className="flex items-end gap-2" onSubmit={(e: FormEvent) => { e.preventDefault(); patch.mutate({ assignee }); }}>
            <Field label="Assignee" value={assignee} onChange={(e) => setAssignee(e.target.value)} maxLength={64} />
            <Button type="submit" size="sm" variant="secondary">Assign</Button>
          </form>
          {i.status !== "acknowledged" && i.status !== "closed" && <Button size="sm" variant="secondary" onClick={() => patch.mutate({ status: "acknowledged" })}>Acknowledge</Button>}
          {i.status !== "closed" ? (
            <Button size="sm" onClick={() => patch.mutate({ status: "closed" })}>Close incident</Button>
          ) : (
            <Button size="sm" variant="secondary" onClick={() => patch.mutate({ status: "open" })}>Reopen</Button>
          )}
        </div>
      )}
      <section>
        <h3 className="mb-2 text-[13px] font-semibold">Alerts in this incident</h3>
        <ul className="space-y-1.5 text-[13px]">
          {i.alerts.map((a) => (
            <li key={a.id} className="flex items-center gap-2">
              <SeverityBadge severity={a.severity} />
              <span className="flex-1">{a.kind.replace(/_/g, " ")} · {a.action ?? "no action"}</span>
              <span className="text-muted">{fmtTime(a.t)}</span>
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h3 className="mb-2 text-[13px] font-semibold">Notes</h3>
        {i.notes.length === 0 && <p className="text-[13px] text-muted">No notes yet.</p>}
        <ul className="space-y-2">
          {i.notes.map((n) => (
            <li key={n.id} className="rounded-[10px] border border-line bg-surface/60 p-2.5 text-[13px]">
              <div className="mb-1 text-[12px] text-muted">{n.username} · {fmtAgo(n.t)}</div>
              <p className="whitespace-pre-wrap">{n.text}</p>
            </li>
          ))}
        </ul>
        {canEdit && (
          <form className="mt-3 space-y-2" onSubmit={(e: FormEvent) => { e.preventDefault(); if (note.trim()) addNote.mutate(note.trim()); }}>
            <label htmlFor="note" className="block text-[13px] font-medium">Add a note</label>
            <textarea id="note" value={note} onChange={(e) => setNote(e.target.value)} maxLength={4000} rows={3}
                      className="w-full rounded-[10px] border border-line bg-surface p-2.5 text-sm text-fg" />
            <Button type="submit" size="sm" disabled={!note.trim()} loading={addNote.isPending}>Add note</Button>
          </form>
        )}
      </section>
    </div>
  );
}

function IncidentsTab() {
  const [status, setStatus] = useState<"" | "open" | "acknowledged" | "closed">("open");
  const [selected, setSelected] = useState<number | null>(null);
  const list = useQuery({
    queryKey: ["alerts", "incidents-list", status],
    queryFn: () => api<Page<Incident>>(`/api/incidents?limit=200${status ? `&status=${status}` : ""}`),
    refetchInterval: 15000,
  });
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_520px]">
      <DataSurface className="p-0">
        <div className="flex gap-2 border-b border-line px-4 py-2.5" role="group" aria-label="Filter incidents">
          {(["open", "acknowledged", "closed", ""] as const).map((s) => (
            <button key={s || "all"} onClick={() => setStatus(s)} aria-pressed={status === s}
                    className={cn("rounded-full border px-3 py-1 text-[12px] capitalize", status === s ? "border-primary bg-primary/15" : "border-line text-muted")}>
              {s || "all"}
            </button>
          ))}
        </div>
        {list.isLoading ? (
          <div className="space-y-2 p-4">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-8 w-full" />)}</div>
        ) : !list.data?.items.length ? (
          <EmptyState icon={FolderOpen} title="No incidents here">Alerts on the same rule are grouped into one incident.</EmptyState>
        ) : (
          <ul aria-label="Incidents">
            {list.data.items.map((i) => (
              <li key={i.id}>
                <button onClick={() => setSelected(i.id)} aria-current={i.id === selected ? "true" : undefined}
                        className={cn("flex w-full items-center gap-3 border-b border-line px-4 py-3 text-left hover:bg-surface-2", i.id === selected && "bg-primary/10")}>
                  <SeverityBadge severity={i.severity} />
                  <span className="min-w-0 flex-1 truncate text-[13.5px]">{i.title}</span>
                  <span className="tabular text-[12px] text-muted">{i.alert_count} alerts · {fmtAgo(i.updated_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </DataSurface>
      <GlassCard>{selected ? <IncidentPanel id={selected} /> : <EmptyState icon={FolderOpen} title="Select an incident">Assign it, add notes and close it here.</EmptyState>}</GlassCard>
    </div>
  );
}

export function Alerts() {
  const [tab, setTab] = useState<"alerts" | "incidents">("alerts");
  const markSeen = useLive((s) => s.markSeen);
  useEffect(() => markSeen(), [markSeen]);
  return (
    <div className="space-y-4">
      <div role="tablist" aria-label="Alerts and incidents" className="flex gap-2">
        {(["alerts", "incidents"] as const).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
                  className={cn("rounded-[10px] px-4 py-2 text-[13.5px] capitalize", tab === t ? "bg-primary/15 font-medium" : "text-muted hover:bg-white/5")}>
            {t}
          </button>
        ))}
      </div>
      {tab === "alerts" ? <AlertsTab /> : <IncidentsTab />}
    </div>
  );
}
