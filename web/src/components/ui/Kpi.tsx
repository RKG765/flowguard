import { useEffect, useRef, useState, type ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";
import { usePrefs } from "@/lib/prefs";
import { GlassCard, Skeleton, type Tone } from "./primitives";

/** Animated count-up (off under reduced motion). */
function useCountUp(target: number | null, ms = 600): number | null {
  const reduced = usePrefs((s) => s.reducedMotion);
  const [value, setValue] = useState<number | null>(target);
  const from = useRef(0);
  useEffect(() => {
    if (target === null) {
      setValue(null);
      return;
    }
    const osReduced = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced || osReduced) {
      setValue(target);
      return;
    }
    const start = performance.now();
    const a = from.current;
    let raf = 0;
    const tick = (now: number) => {
      const k = Math.min(1, (now - start) / ms);
      setValue(a + (target - a) * (1 - Math.pow(1 - k, 3)));
      if (k < 1) raf = requestAnimationFrame(tick);
      else from.current = target;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms, reduced]);
  return value;
}

const ICON_TONE: Record<Tone, string> = {
  ok: "text-ok bg-ok/10", warn: "text-warn bg-warn/10", danger: "text-danger bg-danger/10",
  info: "text-info bg-info/10", ml: "text-ml bg-ml/10", muted: "text-muted bg-white/5",
};

export interface KpiProps {
  label: string;
  value: number | null;
  /** formats the (animated) number; default: integer */
  format?: (v: number) => string;
  unit?: string;
  icon: LucideIcon;
  tone?: Tone;
  caption?: ReactNode;
  loading?: boolean;
  /** shown instead of a number when the value is not available (never invent one) */
  empty?: string;
}

export function Kpi({ label, value, format = (v) => String(Math.round(v)), unit, icon: Icon, tone = "info", caption, loading, empty = "No data yet" }: KpiProps) {
  const shown = useCountUp(value);
  return (
    <GlassCard className="flex min-h-[132px] flex-col justify-between">
      <div className="flex items-start justify-between">
        <span className="text-[13px] font-medium text-muted">{label}</span>
        <span className={cn("rounded-[10px] p-2", ICON_TONE[tone])}>
          <Icon aria-hidden className="h-4 w-4" />
        </span>
      </div>
      {loading ? (
        <Skeleton className="h-8 w-24" />
      ) : value === null || shown === null ? (
        <span className="text-sm text-muted">{empty}</span>
      ) : (
        <span className="tabular text-[28px] font-semibold leading-8 tracking-tight" aria-label={`${label}: ${format(value)}${unit ? ` ${unit}` : ""}`}>
          {format(shown)}
          {unit && <span className="ml-1 text-sm font-medium text-muted">{unit}</span>}
        </span>
      )}
      {caption && <div className="text-[12px] text-muted">{caption}</div>}
    </GlassCard>
  );
}
