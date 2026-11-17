import { useState } from "react";
import { FlaskConical, RotateCcw, ShieldCheck, Wrench } from "lucide-react";
import { cn, fmtTime } from "@/lib/cn";
import { LINKS, SWITCHES, useDemo, type Kind, type SimRule } from "@/lib/demo";
import { Badge, Banner, Button, CardTitle, GlassCard, RuleStatusBadge, SeverityBadge, type Tone } from "@/components/ui/primitives";
import { PortStrip, TagStripe } from "@/components/ui/Patch";

const SCENARIOS: { kind: Kind; label: string; text: string; severity: string }[] = [
  { kind: "altered", label: "Change a rule", text: "A signed rule's action is rewritten on the switch.", severity: "high" },
  { kind: "forged", label: "Add an unknown rule", text: "A rule the controller never installed appears.", severity: "critical" },
  { kind: "missing", label: "Delete a rule", text: "A signed rule disappears from the flow table.", severity: "medium" },
  { kind: "shadow", label: "Hide a rule", text: "An unknown higher-priority rule takes over its traffic.", severity: "critical" },
  { kind: "unattributed_change", label: "Change and revert", text: "A rule is changed and put back before a poll would see it.", severity: "high" },
];
const SEVERITY = Object.fromEntries(SCENARIOS.map((s) => [s.kind, s.severity]));
const show = (s: SimRule["status"]) => (s === "unattributed_change" ? "altered" : s);
const RANK: Record<string, number> = { ok: 0, missing: 2, altered: 3, shadow: 3, forged: 3 };

function health(rules: SimRule[]): { tone: Tone; label: string } {
  const worst = rules.reduce((w, r) => Math.max(w, RANK[show(r.status)] ?? 0), 0);
  return worst >= 3 ? { tone: "danger", label: "Tampered" } : worst === 2 ? { tone: "warn", label: "Rule missing" } : { tone: "ok", label: "Verified" };
}
const RING: Record<Tone, string> = { ok: "rgb(var(--ok))", warn: "rgb(var(--warn))", danger: "rgb(var(--danger))", info: "rgb(var(--info))", ml: "rgb(var(--ml))", muted: "rgb(var(--line))" };

function Topo({ selected, onSelect }: { selected: string; onSelect: (id: string) => void }) {
  const rules = useDemo((s) => s.rules);
  const at = (id: string) => SWITCHES.find((s) => s.id === id)!;
  return (
    <div className="overflow-x-auto"><svg viewBox="0 0 600 300" role="group" aria-label="Simulated topology: one core switch, three edge switches, six hosts" className="h-auto w-full min-w-[520px]">
      {SWITCHES.map((s) => <line key={`e-${s.id}`} x1="300" y1="28" x2={s.x} y2={s.y} stroke="rgb(var(--line))" strokeDasharray="4 4" />)}
      {LINKS.map(([a, b]) => <line key={a + b} x1={at(a).x} y1={at(a).y} x2={at(b).x} y2={at(b).y} stroke="rgb(var(--muted))" strokeWidth="2" />)}
      {SWITCHES.flatMap((s) => s.hosts.map((h, i) => {
        const hx = s.x + (i ? 36 : -36);
        return (
          <g key={h}>
            <line x1={s.x} y1={s.y} x2={hx} y2={278} stroke="rgb(var(--line))" />
            <rect x={hx - 16} y={268} width="32" height="20" rx="3" fill="rgb(var(--surface-2))" stroke="rgb(var(--line))" />
            <text x={hx} y={282} textAnchor="middle" fontSize="11" fill="rgb(var(--muted))" fontFamily="JetBrains Mono, monospace">{h}</text>
          </g>
        );
      }))}
      <rect x="236" y="8" width="128" height="40" rx="3" fill="rgb(var(--rail))" stroke="rgb(var(--line))" />
      <text x="300" y="24" textAnchor="middle" fontSize="12" fill="#e6ebf2" fontFamily="Barlow Condensed, sans-serif" letterSpacing="1.2">FLOWGUARD ENGINE</text>
      <text x="300" y="39" textAnchor="middle" fontSize="10.5" fill="#a9b6c8">signs + verifies every rule</text>
      {SWITCHES.map((s) => {
        const h = health(rules.filter((r) => r.sw === s.id));
        return (
          <g key={s.id} role="button" tabIndex={0} aria-label={`Switch ${s.id} ${s.name}: ${h.label}`} aria-pressed={selected === s.id}
             onClick={() => onSelect(s.id)} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onSelect(s.id)} className="cursor-pointer">
            <rect x={s.x - 56} y={s.y - 26} width="112" height="52" rx="3" fill="rgb(var(--surface))" stroke={RING[h.tone]} strokeWidth={selected === s.id ? 4 : 2.5} />
            <text x={s.x} y={s.y - 6} textAnchor="middle" fontSize="15" fontWeight="600" fill="rgb(var(--fg))" fontFamily="Barlow Condensed, sans-serif" letterSpacing="1">{s.id.toUpperCase()} · {s.name}</text>
            <text x={s.x} y={s.y + 14} textAnchor="middle" fontSize="12" fill={RING[h.tone]} fontWeight="600">{h.label}</text>
          </g>
        );
      })}
    </svg></div>
  );
}

/** Simulated L2/L3/risk for one switch, using the default policy weights (l1 1.0, l2 0.8, l3 0.4) and thresholds. */
function layers(rs: SimRule[]) {
  const bad = rs.filter((r) => r.status !== "ok");
  const l1 = bad.length ? 1 : 0;
  const l2 = bad.some((r) => r.status !== "forged") ? 1 : 0; // forwarding differs unless the rule is only an extra one
  const l3 = Math.min(1, bad.length * 0.35 + (bad.some((r) => r.status === "forged" || r.status === "shadow") ? 0.3 : 0));
  const risk = Math.max(l1 ? 0.5 : 0, (l1 + 0.8 * l2 + 0.4 * l3) / 2.2); // a failed signature never scores below the restore threshold
  const action = risk >= 0.8 ? "quarantine port" : risk >= 0.5 ? "restore + alert" : risk >= 0.3 ? "alert" : "none";
  return { l1, l2, l3, risk, action };
}

export function Demo() {
  const { rules, events, autoRepair, run, repair, reset, setAuto } = useDemo();
  const [sw, setSw] = useState("s2");
  const open = events.filter((e) => e.restoreMs === null).length;
  return (
    <div className="space-y-5">
      <Banner tone="info" icon={FlaskConical}>
        <strong>Simulated lab.</strong> This page edits an in-browser model of four switches. It sends nothing to any switch or to the engine, and FlowGuard itself runs no attacks. It shows what FlowGuard's check would report if someone changed the rules.
      </Banner>

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <GlassCard className="xl:col-span-2">
          <CardTitle icon={ShieldCheck} aside={<Badge tone="ml">Simulated</Badge>}>Topology: pick a switch</CardTitle>
          <Topo selected={sw} onSelect={setSw} />
        </GlassCard>

        <GlassCard>
          <CardTitle icon={FlaskConical}>Simulate tampering on {sw.toUpperCase()}</CardTitle>
          <ul className="space-y-2">
            {SCENARIOS.map((s) => (
              <li key={s.kind}>
                <button onClick={() => run(s.kind, sw)} className="w-full rounded-[3px] border border-line bg-surface-2 px-3 py-2 text-left hover:border-primary">
                  <span className="block text-[14px] font-semibold">{s.label}</span>
                  <span className="block text-[12.5px] text-muted">{s.text}</span>
                </button>
              </li>
            ))}
          </ul>
          <label className="mt-4 flex items-center gap-2 text-[13px]">
            <input type="checkbox" checked={autoRepair} onChange={(e) => setAuto(e.target.checked)} className="h-4 w-4 accent-[rgb(var(--primary))]" />
            Auto-repair (engine restores the signed rule)
          </label>
          <div className="mt-3 flex gap-2">
            <Button onClick={repair} disabled={!open}><Wrench aria-hidden className="h-4 w-4" /> Repair now</Button>
            <Button variant="secondary" onClick={reset}><RotateCcw aria-hidden className="h-4 w-4" /> Reset</Button>
          </div>
        </GlassCard>
      </section>

      <GlassCard>
        <CardTitle icon={ShieldCheck}>Patch panel by switch</CardTitle>
        <div className="space-y-3">
          {SWITCHES.map((s) => {
            const rs = rules.filter((r) => r.sw === s.id);
            const h = health(rs);
            return (
              <div key={s.id} className="flex items-center gap-4">
                <span className="label w-32 !text-fg">{s.id.toUpperCase()} · {s.name}</span>
                <Badge tone={h.tone}>{h.label}</Badge>
                <div className="min-w-0 flex-1"><PortStrip ports={rs.map((r) => ({ status: show(r.status), label: `T${r.table} · P${r.priority}`, cookie: r.foundCookie, against: r.signedCookie }))} /></div>
              </div>
            );
          })}
        </div>
      </GlassCard>

      <GlassCard>
        <CardTitle icon={ShieldCheck} aside={<Badge tone="ml">Simulated</Badge>}>L2 probes, L3 score and fused risk</CardTitle>
        <table className="w-full text-left text-[13px]">
          <thead><tr><th className="label py-1 pr-3">Switch</th><th className="label py-1 pr-3">L1 signed rules</th><th className="label py-1 pr-3">L2 canary probe</th><th className="label py-1 pr-3">L3 anomaly score</th><th className="label py-1 pr-3">Fused risk</th><th className="label py-1">Policy action</th></tr></thead>
          <tbody>{SWITCHES.map((s) => {
            const l = layers(rules.filter((r) => r.sw === s.id));
            return (
              <tr key={s.id} className="border-t border-line">
                <td className="py-2 pr-3 font-semibold">{s.id.toUpperCase()}</td>
                <td className="pr-3">{l.l1 ? <Badge tone="danger">Mismatch</Badge> : <Badge tone="ok">Match</Badge>}</td>
                <td className="pr-3">{l.l2 ? <Badge tone="danger">Forwarding differs</Badge> : <Badge tone="ok">Pass</Badge>}</td>
                <td className="tabular pr-3">{l.l3.toFixed(2)}</td>
                <td className="tabular pr-3 font-mono">{l.risk.toFixed(2)}</td>
                <td>{l.action}</td>
              </tr>
            );
          })}</tbody>
        </table>
        <p className="mt-2 text-[12px] text-muted">Risk = (1.0 x L1 + 0.8 x L2 + 0.4 x L3) / 2.2, and never below 0.50 when a signed rule fails verification. Thresholds: alert 0.30, restore 0.50, quarantine 0.80. These numbers are simulated; the real L2 prober and L3 scorer run inside the engine (see the Probes and ML pages).</p>
      </GlassCard>

      <GlassCard>
        <CardTitle aside={<span className="text-[12px] text-muted">{open} unresolved</span>}>What FlowGuard caught</CardTitle>
        {!events.length ? (
          <p className="text-[13px] text-muted">Nothing yet. Pick a switch and run a scenario above.</p>
        ) : (
          <ol className="space-y-3" aria-live="polite">
            {events.map((e) => (
              <li key={e.id} className={cn("-mx-5 border-t border-line px-5 py-3", e.restoreMs === null && "row-lit")}>
                <div className="flex flex-wrap items-center gap-2">
                  <SeverityBadge severity={SEVERITY[e.kind] ?? "high"} />
                  <RuleStatusBadge status={e.kind === "unattributed_change" ? "altered" : e.kind} />
                  <span className="mono text-muted">{fmtTime(e.t)} · {e.sw}</span>
                  <span className="ml-auto text-[13px]">Detected in <strong className="tabular">{e.detectMs} ms</strong> · {e.restoreMs === null ? "repair pending" : <>restored in <strong className="tabular">{e.restoreMs} ms</strong></>}</span>
                </div>
                <p className="mt-2 text-[13.5px]">{e.summary}</p>
                <div className="mt-2 grid grid-cols-1 gap-3 md:grid-cols-2">
                  <div><div className="label mb-1">Signed by the controller</div><div className="mono">{e.signed ?? "(no signed rule)"}</div><div className="mt-1 flex items-center gap-2"><TagStripe cookie={e.signedCookie} /><span className="mono text-muted">{e.signedCookie ?? "-"}</span></div></div>
                  <div><div className="label mb-1">Found on the switch</div><div className="mono">{e.found ?? "(rule absent)"}</div><div className="mt-1 flex items-center gap-2">{e.foundCookie ? <TagStripe cookie={e.foundCookie} against={e.signedCookie} /> : null}<span className="mono text-muted">{e.foundCookie ?? "-"}</span></div></div>
                </div>
              </li>
            ))}
          </ol>
        )}
      </GlassCard>

      <GlassCard>
        <CardTitle>What FlowGuard does</CardTitle>
        <ol className="grid grid-cols-1 gap-3 text-[13.5px] md:grid-cols-4">
          <li><strong>1 · Sign.</strong> The controller installs every rule with an HMAC tag in its cookie. The stripe is that tag.</li>
          <li><strong>2 · Watch.</strong> The engine sees every change on the switch as it happens.</li>
          <li><strong>3 · Compare.</strong> A rule with no valid tag, a different tag, or no rule at all is flagged within milliseconds.</li>
          <li><strong>4 · Repair.</strong> The signed rule is put back and the alert records detect and restore times.</li>
        </ol>
      </GlassCard>
    </div>
  );
}
