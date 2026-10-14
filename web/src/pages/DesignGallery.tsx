import { useEffect, useState, type ReactNode } from "react";
import { Bell, Clock, ShieldCheck, ShieldHalf } from "lucide-react";
import { contrast, over, parseTriplet } from "@/lib/contrast";
import { usePrefs } from "@/lib/prefs";
import { Kpi } from "@/components/ui/Kpi";
import {
  Badge, Banner, Button, CardTitle, DataSurface, EmptyState, Field, GlassCard, ModeBadge, RULE_STATUS, RuleStatusBadge, SEVERITY, SeverityBadge, Skeleton,
} from "@/components/ui/primitives";

const TEXT_TOKENS = ["fg", "muted", "primary", "ok", "warn", "danger", "info", "ml"] as const;

function useTokens(theme: string) {
  const [vals, setVals] = useState<Record<string, string>>({});
  useEffect(() => {
    const cs = getComputedStyle(document.documentElement);
    const names = [...TEXT_TOKENS, "bg", "surface", "surface-2", "line", "glass-alpha"];
    setVals(Object.fromEntries(names.map((n) => [n, cs.getPropertyValue(`--${n}`).trim()])));
  }, [theme]);
  return vals;
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <GlassCard>
      <CardTitle>{title}</CardTitle>
      {children}
    </GlassCard>
  );
}

/** Living style guide: every component in every state, with contrast measured on the current theme's tokens. */
export function DesignGallery() {
  const prefs = usePrefs();
  const tokens = useTokens(prefs.theme);
  const ready = tokens.bg && tokens.surface;
  const glassBg = ready ? over([255, 255, 255], Number(tokens["glass-alpha"] || 0.07), parseTriplet(tokens.bg!)) : null;

  return (
    <div className="space-y-5">
      <Section title="Display preferences">
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={prefs.toggleTheme}>Theme: {prefs.theme}</Button>
          <Button variant="secondary" onClick={() => prefs.setReducedMotion(!prefs.reducedMotion)} aria-pressed={prefs.reducedMotion}>
            Reduced motion: {prefs.reducedMotion ? "on" : "off"}
          </Button>
          <Button variant="secondary" onClick={() => prefs.setReducedTransparency(!prefs.reducedTransparency)} aria-pressed={prefs.reducedTransparency}>
            Reduced transparency: {prefs.reducedTransparency ? "on" : "off"}
          </Button>
        </div>
        <p className="mt-3 text-[12.5px] text-muted">The operating-system settings (prefers-reduced-motion, prefers-reduced-transparency) are honoured as well.</p>
      </Section>

      <Section title="Color tokens and measured contrast (WCAG AA needs 4.5 for text)">
        {!ready ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <DataSurface className="overflow-x-auto p-0">
            <table className="w-full text-left text-[13px]">
              <thead className="text-[11px] uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-4 py-2">Token</th><th className="px-3 py-2">Sample</th>
                  <th className="px-3 py-2 text-right">on bg</th><th className="px-3 py-2 text-right">on surface</th><th className="px-3 py-2 text-right">on glass</th>
                </tr>
              </thead>
              <tbody>
                {TEXT_TOKENS.map((t) => {
                  const fg = parseTriplet(tokens[t]!);
                  const cells = [parseTriplet(tokens.bg!), parseTriplet(tokens.surface!), glassBg!].map((b) => contrast(fg, b));
                  return (
                    <tr key={t} className="border-t border-line">
                      <td className="mono px-4 py-2">--{t}</td>
                      <td className="px-3 py-2" style={{ color: `rgb(${tokens[t]})` }}>Sample text 123</td>
                      {cells.map((c, i) => (
                        <td key={i} className={`tabular px-3 py-2 text-right ${c >= 4.5 ? "" : "text-danger"}`}>
                          {c.toFixed(2)} {c >= 4.5 ? "✓" : "✗"}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </DataSurface>
        )}
      </Section>

      <Section title="Typography">
        <div className="space-y-2">
          <div className="text-[32px] font-semibold tracking-tight">Display 32 / semibold</div>
          <div className="text-xl font-semibold">Headline 20 / semibold</div>
          <div className="text-[15px] font-semibold">Title 15 / semibold</div>
          <div className="text-sm">Body 14: FlowGuard detects unauthorized changes to OpenFlow rules.</div>
          <div className="text-[12px] font-medium uppercase tracking-wide text-muted">Label 12</div>
          <div className="mono">priority=100,tcp,tp_dst=23 actions=drop · cookie=0x3fdfe39c20001 · dpid 0000000000000001</div>
          <div className="tabular text-[28px] font-semibold">1,234.5 ms (tabular numerals)</div>
        </div>
      </Section>

      <Section title="Buttons">
        <div className="flex flex-wrap items-center gap-2">
          <Button>Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="danger">Restore rule</Button>
          <Button size="sm">Small</Button>
          <Button loading>Loading</Button>
          <Button disabled>Disabled</Button>
          <Button variant="ghost" size="icon" aria-label="Notifications"><Bell aria-hidden className="h-4 w-4" /></Button>
        </div>
      </Section>

      <Section title="Form fields">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <Field label="Username" defaultValue="analyst" hint="3-64 letters, digits, . _ -" />
          <Field label="Password" type="password" defaultValue="short" error="At least 8 characters" />
          <Field label="Disabled" disabled defaultValue="read only" />
        </div>
      </Section>

      <Section title="Banners">
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
          <Banner tone="danger">Invalid username or password.</Banner>
          <Banner tone="warn" icon={Clock}>Too many failed attempts. Try again in 58 s.</Banner>
          <Banner tone="info">This runs only on this machine (127.0.0.1).</Banner>
          <Banner tone="ok">Rule restored in 7 ms.</Banner>
        </div>
      </Section>

      <Section title="Badges (always icon + label)">
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">{Object.keys(RULE_STATUS).map((s) => <RuleStatusBadge key={s} status={s} />)}</div>
          <div className="flex flex-wrap gap-2">{Object.keys(SEVERITY).map((s) => <SeverityBadge key={s} severity={s} />)}</div>
          <div className="flex flex-wrap gap-2"><ModeBadge mode="live" /><ModeBadge mode="replay" /><ModeBadge mode="simulated" /><Badge>WSL2</Badge></div>
        </div>
      </Section>

      <Section title="KPI cards: value, loading, no data">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <Kpi label="Protected rules" value={3} icon={ShieldHalf} caption="example value in the style guide" />
          <Kpi label="Verified" value={null} icon={ShieldCheck} tone="ok" loading />
          <Kpi label="Mean detect time" value={null} icon={Clock} empty="No alerts yet" />
        </div>
      </Section>

      <Section title="Surfaces">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <GlassCard><p className="text-sm">Glass container (cards, sidebar, top bar, dialogs).</p></GlassCard>
          <DataSurface className="p-5"><p className="mono">Opaque data surface for tables, rule diffs and logs.</p></DataSurface>
        </div>
      </Section>

      <Section title="Empty state">
        <EmptyState icon={ShieldCheck} title="No incidents">Nothing has been tampered with since FlowGuard started recording.</EmptyState>
      </Section>
    </div>
  );
}
