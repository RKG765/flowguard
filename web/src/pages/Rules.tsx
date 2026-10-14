import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, Search, ShieldHalf } from "lucide-react";
import { api, type RulesSummary } from "@/lib/api";
import { cn, fmtAgo } from "@/lib/cn";
import { csvCell, formatInstructions, formatMatch, shortCookie } from "@/lib/format";
import type { RuleRow, SwitchRow } from "@/lib/types";
import { useWindow } from "@/lib/useWindow";
import { RepairButton } from "@/components/rules/RepairButton";
import { RuleDiff } from "@/components/rules/RuleDiff";
import { Button, CardTitle, DataSurface, EmptyState, GlassCard, RULE_STATUS, RuleStatusBadge, Skeleton } from "@/components/ui/primitives";

const ROW_H = 44;
const VIEWPORT = 520;
const STATUSES = ["ok", "altered", "shadow", "forged", "missing", "pending"] as const;
const rowKey = (r: RuleRow) => `${r.dpid}|${r.table_id}|${r.priority}|${JSON.stringify(r.match)}`;

function exportCsv(rows: RuleRow[]) {
  const head = ["dpid", "table_id", "priority", "status", "match", "actions", "cookie", "signed_cookie", "last_verified"];
  const lines = rows.map((r) =>
    [r.dpid, r.table_id, r.priority, r.status, formatMatch(r.match), formatInstructions(r.instructions).join(" | "), r.cookie ?? "", r.golden_cookie ?? "",
     new Date(r.last_verified * 1000).toISOString()].map(csvCell).join(","),
  );
  const blob = new Blob([[head.join(","), ...lines].join("\n")], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "flowguard-rules.csv";
  a.click();
  URL.revokeObjectURL(a.href);
}

export function Rules() {
  const [dpid, setDpid] = useState<string>("");
  const [status, setStatus] = useState<string>("");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const switches = useQuery({ queryKey: ["rules", "switches"], queryFn: () => api<SwitchRow[]>("/api/switches"), refetchInterval: 15000 });
  const summary = useQuery({ queryKey: ["rules", "summary"], queryFn: () => api<RulesSummary>("/api/rules/summary"), refetchInterval: 10000 });
  const rules = useQuery({
    queryKey: ["rules", "list", dpid],
    queryFn: () => api<RuleRow[]>(`/api/rules${dpid ? `?dpid=${encodeURIComponent(dpid)}` : ""}`),
    refetchInterval: 10000,
  });

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (rules.data ?? []).filter(
      (r) => (!status || r.status === status) &&
        (!needle || `${formatMatch(r.match)} ${formatInstructions(r.instructions).join(" ")} ${r.cookie ?? ""} ${r.priority}`.toLowerCase().includes(needle)),
    );
  }, [rules.data, status, q]);
  const win = useWindow(filtered.length, ROW_H, VIEWPORT);
  const sel = filtered.find((r) => rowKey(r) === selected) ?? (rules.data ?? []).find((r) => rowKey(r) === selected) ?? null;

  return (
    <div className="grid grid-cols-1 gap-4 2xl:grid-cols-[1fr_440px]">
      <div className="space-y-4">
        <GlassCard className="py-4">
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-[12px] text-muted">
              Switch
              <select value={dpid} onChange={(e) => setDpid(e.target.value)} className="mt-1 block h-9 rounded-[10px] border border-line bg-surface px-2 text-sm text-fg">
                <option value="">All switches</option>
                {(switches.data ?? []).map((s) => <option key={s.dpid} value={s.dpid}>{s.dpid}</option>)}
              </select>
            </label>
            <label className="min-w-[240px] flex-1 text-[12px] text-muted">
              Search match, actions, cookie
              <span className="relative mt-1 block">
                <Search aria-hidden className="absolute left-2.5 top-2.5 h-4 w-4" />
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. tcp_dst=23" className="h-9 w-full rounded-[10px] border border-line bg-surface pl-8 pr-2 text-sm text-fg" />
              </span>
            </label>
            <Button variant="secondary" size="sm" onClick={() => exportCsv(filtered)} disabled={!filtered.length}>
              <Download aria-hidden className="h-4 w-4" /> Export CSV
            </Button>
          </div>
          <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Filter by status">
            <button onClick={() => setStatus("")} aria-pressed={!status} className={cn("rounded-full border px-3 py-1 text-[12px]", !status ? "border-primary bg-primary/15" : "border-line text-muted")}>
              All {summary.data ? `(${summary.data.rules})` : ""}
            </button>
            {STATUSES.map((s) => (
              <button key={s} onClick={() => setStatus(s)} aria-pressed={status === s}
                      className={cn("rounded-full border px-3 py-1 text-[12px]", status === s ? "border-primary bg-primary/15" : "border-line text-muted")}>
                {RULE_STATUS[s]!.label} {summary.data ? `(${summary.data.by_status[s] ?? 0})` : ""}
              </button>
            ))}
          </div>
        </GlassCard>

        <DataSurface className="p-0">
          {rules.isLoading ? (
            <div className="space-y-2 p-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-7 w-full" />)}</div>
          ) : rules.isError ? (
            <EmptyState icon={ShieldHalf} title="Could not load rules">Check that the FlowGuard core is running.</EmptyState>
          ) : !filtered.length ? (
            <EmptyState icon={ShieldHalf} title={rules.data?.length ? "No rule matches these filters" : "No rules reported yet"}>
              {rules.data?.length ? "Clear the search or pick another status." : "Rules appear after the engine's first verification pass of a connected switch."}
            </EmptyState>
          ) : (
            <div role="table" aria-label="Flow rules" aria-rowcount={filtered.length + 1}>
              <div role="rowgroup">
                <div className="grid grid-cols-[110px_150px_56px_70px_1fr_1fr] gap-2 border-b border-line px-4 py-2 text-[11px] font-medium uppercase tracking-wide text-muted" role="row" aria-rowindex={1}>
                  <span role="columnheader">Status</span><span role="columnheader">Switch</span><span role="columnheader">Table</span>
                  <span role="columnheader">Priority</span><span role="columnheader">Match</span><span role="columnheader">Actions</span>
                </div>
              </div>
              <div role="rowgroup" style={{ maxHeight: VIEWPORT }} className="overflow-y-auto" onScroll={win.onScroll}>
              <div aria-hidden style={{ height: win.padTop }} />
              {filtered.slice(win.first, win.last).map((r, i) => {
                const k = rowKey(r);
                return (
                  <button key={k} role="row" aria-rowindex={win.first + i + 2} onClick={() => setSelected(k)} aria-selected={k === selected}
                          className={cn("grid w-full grid-cols-[110px_150px_56px_70px_1fr_1fr] items-center gap-2 border-b border-line px-4 text-left text-[13px] hover:bg-surface-2",
                                        k === selected && "bg-primary/10")} style={{ height: ROW_H }}>
                    <span role="cell"><RuleStatusBadge status={r.status} /></span>
                    <span role="cell" className="mono truncate text-muted">{r.dpid}</span>
                    <span role="cell" className="tabular">{r.table_id}</span>
                    <span role="cell" className="tabular">{r.priority}</span>
                    <span role="cell" className="mono truncate">{formatMatch(r.match)}</span>
                    <span role="cell" className="mono truncate text-muted">{r.present ? formatInstructions(r.instructions).join(" ; ") : "(not on the switch)"}</span>
                  </button>
                );
              })}
              <div aria-hidden style={{ height: win.padBottom }} />
              </div>
            </div>
          )}
        </DataSurface>
      </div>

      <aside aria-label="Rule details">
        <GlassCard className="2xl:sticky 2xl:top-24">
          {!sel ? (
            <EmptyState icon={ShieldHalf} title="Select a rule">Its signed version, what the switch holds now and the repair action appear here.</EmptyState>
          ) : (
            <div className="space-y-4">
              <CardTitle aside={<RuleStatusBadge status={sel.status} />}>Rule details</CardTitle>
              <p className="text-[13px] text-muted">{RULE_STATUS[sel.status]?.help}</p>
              <dl className="grid grid-cols-[110px_1fr] gap-y-1.5 text-[13px]">
                <dt className="text-muted">Switch</dt><dd className="mono">{sel.dpid}</dd>
                <dt className="text-muted">Table / priority</dt><dd className="tabular">{sel.table_id} / {sel.priority}</dd>
                <dt className="text-muted">Match</dt><dd className="mono break-all">{formatMatch(sel.match)}</dd>
                <dt className="text-muted">Cookie</dt><dd className="mono">{shortCookie(sel.cookie)}</dd>
                <dt className="text-muted">Last verified</dt><dd>{fmtAgo(sel.last_verified)}</dd>
              </dl>
              <RuleDiff signed={sel.golden ? (sel.golden_instructions ?? sel.instructions) : null} observed={sel.instructions}
                        signedCookie={sel.golden_cookie} observedCookie={sel.cookie} present={sel.present} />
              <RepairButton target={sel} onDone={() => void rules.refetch()} />
            </div>
          )}
        </GlassCard>
      </aside>
    </div>
  );
}
