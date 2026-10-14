import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Background, Controls, Handle, Position, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Cpu, Monitor, Network, Server } from "lucide-react";
import { api } from "@/lib/api";
import { cn, fmtAgo, fmtTime } from "@/lib/cn";
import { useLive } from "@/lib/live";
import { usePrefs } from "@/lib/prefs";
import { formatMatch } from "@/lib/format";
import type { Alert, EngineStatusFull, RuleRow, SwitchRow } from "@/lib/types";
import { Badge, CardTitle, EmptyState, GlassCard, RuleStatusBadge, SeverityBadge, Skeleton, type Tone } from "@/components/ui/primitives";

/** Worst status among a switch's rules decides its colour: tampered > missing > pending > verified. */
const RANK: Record<string, number> = { ok: 0, pending: 1, missing: 2, altered: 3, shadow: 3, forged: 3 };
export function switchHealth(rules: RuleRow[]): { tone: Tone; label: string } {
  const worst = rules.reduce((w, r) => Math.max(w, RANK[r.status] ?? 0), 0);
  if (!rules.length) return { tone: "muted", label: "No rules reported" };
  if (worst >= 3) return { tone: "danger", label: "Tampered rules" };
  if (worst === 2) return { tone: "warn", label: "Missing rules" };
  if (worst === 1) return { tone: "info", label: "Repair in flight" };
  return { tone: "ok", label: "All rules verified" };
}

type NodeData = { label: string; sub?: string; tone: Tone; kind: "engine" | "switch" | "host"; selected?: boolean };
const TONE_RING: Record<Tone, string> = {
  ok: "border-ok/60", warn: "border-warn/60", danger: "border-danger/70", info: "border-info/60", ml: "border-ml/60", muted: "border-line",
};

function FgNode({ data }: NodeProps<Node<NodeData>>) {
  const Icon = data.kind === "engine" ? Cpu : data.kind === "switch" ? Server : Monitor;
  return (
    <div className={cn("glass flex min-w-[150px] items-center gap-2.5 border-2 px-3 py-2", TONE_RING[data.tone], data.selected && "ring-2 ring-primary")}>
      <Handle type="target" position={Position.Top} className="!opacity-0" />
      <Icon aria-hidden className="h-4 w-4 text-muted" />
      <div>
        <div className="text-[12.5px] font-medium">{data.label}</div>
        {data.sub && <div className="mono text-[11px] text-muted">{data.sub}</div>}
      </div>
      <Handle type="source" position={Position.Bottom} className="!opacity-0" />
    </div>
  );
}
const nodeTypes = { fg: FgNode };

export function Topology() {
  const [selected, setSelected] = useState<string | null>(null);
  const reduced = usePrefs((s) => s.reducedMotion);
  const liveEngine = useLive((s) => s.engine);
  const switches = useQuery({ queryKey: ["rules", "switches"], queryFn: () => api<SwitchRow[]>("/api/switches"), refetchInterval: 10000 });
  const rules = useQuery({ queryKey: ["rules", "list", ""], queryFn: () => api<RuleRow[]>("/api/rules"), refetchInterval: 10000 });
  const engine = useQuery({ queryKey: ["rules", "engine"], queryFn: () => api<EngineStatusFull>("/api/engine/status"), refetchInterval: 10000 });
  const detail = useQuery({
    queryKey: ["alerts", "switch", selected],
    queryFn: () => api<{ rules: RuleRow[]; recent_alerts: Alert[] }>(`/api/switches/${encodeURIComponent(selected!)}`),
    enabled: !!selected,
  });

  const { nodes, edges } = useMemo(() => {
    const ns: Node<NodeData>[] = [];
    const es: Edge[] = [];
    const sws = switches.data ?? [];
    const hosts = engine.data?.status?.hosts ?? {};
    const engineUp = !!liveEngine || !!engine.data?.known;
    ns.push({ id: "engine", type: "fg", position: { x: Math.max(0, (sws.length - 1) * 260) / 2, y: 0 },
              data: { label: "FlowGuard engine", sub: "Ryu controller", tone: engineUp ? "ok" : "muted", kind: "engine" } });
    sws.forEach((sw, i) => {
      const h = switchHealth((rules.data ?? []).filter((r) => r.dpid === sw.dpid));
      const id = `sw-${sw.dpid}`;
      ns.push({ id, type: "fg", position: { x: i * 260, y: 140 },
                data: { label: `Switch s${parseInt(sw.dpid, 16)}`, sub: sw.dpid, tone: sw.connected ? h.tone : "muted", kind: "switch", selected: selected === sw.dpid } });
      es.push({ id: `e-${id}`, source: "engine", target: id, animated: sw.connected && !reduced, label: sw.monitor_up ? "OpenFlow · monitored" : "OpenFlow",
                style: { stroke: "rgb(var(--muted))" }, labelStyle: { fill: "rgb(var(--muted))", fontSize: 11 } });
      Object.entries(hosts[sw.dpid] ?? {}).sort((a, b) => a[1] - b[1]).forEach(([mac, port], j) => {
        const hid = `h-${sw.dpid}-${mac}`;
        ns.push({ id: hid, type: "fg", position: { x: i * 260 - 120 + j * 120, y: 290 + (j % 2) * 70 }, data: { label: `Host on port ${port}`, sub: mac, tone: "muted", kind: "host" } });
        es.push({ id: `e-${hid}`, source: id, target: hid, style: { stroke: "rgb(var(--line))" } });
      });
    });
    return { nodes: ns, edges: es };
  }, [switches.data, rules.data, engine.data, liveEngine, selected, reduced]);

  const sel = (switches.data ?? []).find((s) => s.dpid === selected);
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_420px]">
      <GlassCard className="h-[640px] p-2">
        {switches.isLoading ? (
          <Skeleton className="h-full w-full" />
        ) : !switches.data?.length ? (
          <EmptyState icon={Network} title="No switches yet">Switches appear when they connect to the FlowGuard engine.</EmptyState>
        ) : (
          <ReactFlow key={nodes.length} nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ maxZoom: 1, padding: 0.25 }}
                     minZoom={0.3} maxZoom={1.5} proOptions={{ hideAttribution: true }} aria-label="Network topology"
                     nodesDraggable={false} onNodeClick={(_, n) => n.id.startsWith("sw-") && setSelected(n.id.slice(3))} colorMode={usePrefs.getState().theme}>
            <Background gap={24} color="rgb(var(--line))" />
            <Controls showInteractive={false} />
          </ReactFlow>
        )}
      </GlassCard>
      <aside aria-label="Switch details" className="space-y-4">
        <GlassCard>
          {!sel ? (
            <EmptyState icon={Server} title="Select a switch">Its rules and recent alerts appear here.</EmptyState>
          ) : (
            <div className="space-y-3">
              <CardTitle aside={<Badge tone={sel.connected ? "ok" : "warn"}>{sel.connected ? "Connected" : "Disconnected"}</Badge>}>Switch {sel.dpid}</CardTitle>
              <p className="text-[13px] text-muted">Change monitor {sel.monitor_up ? "up" : "down"} · last seen {fmtAgo(sel.last_seen)}</p>
              <h3 className="text-[13px] font-semibold">Protected rules</h3>
              {detail.isLoading ? <Skeleton className="h-20 w-full" /> : (
                <ul className="space-y-1.5">
                  {(detail.data?.rules ?? []).map((r) => (
                    <li key={`${r.table_id}-${r.priority}-${JSON.stringify(r.match)}`} className="flex items-center gap-2 text-[12.5px]">
                      <RuleStatusBadge status={r.status} />
                      <span className="mono truncate">p{r.priority} {formatMatch(r.match)}</span>
                    </li>
                  ))}
                </ul>
              )}
              <h3 className="text-[13px] font-semibold">Recent alerts</h3>
              {!detail.data?.recent_alerts.length ? <p className="text-[13px] text-muted">None.</p> : (
                <ul className="space-y-1.5">
                  {detail.data.recent_alerts.slice(0, 8).map((a) => (
                    <li key={a.id} className="flex items-center gap-2 text-[12.5px]">
                      <SeverityBadge severity={a.severity} />
                      <span className="flex-1 truncate">{a.kind.replace(/_/g, " ")}</span>
                      <span className="text-muted">{fmtTime(a.t)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </GlassCard>
        <p className="px-1 text-[12px] text-muted">
          Hosts are the ones the switch has learned from traffic. Links between switches are not discovered yet, so multi-switch labs show each switch on its own.
        </p>
      </aside>
    </div>
  );
}
