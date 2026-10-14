import { forwardRef, type ButtonHTMLAttributes, type HTMLAttributes, type InputHTMLAttributes, type ReactNode } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { AlertTriangle, CircleDashed, Info, Loader2, ShieldAlert, ShieldCheck, Sparkles, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";

/* ---- surfaces ---------------------------------------------------------------------------------------------------- */
/** Glass container: cards, panels. Use DataSurface for tables, rule diffs and logs instead. */
export function GlassCard({ className, ...p }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("glass p-5", className)} {...p} />;
}
export function DataSurface({ className, ...p }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("data-surface", className)} {...p} />;
}
export function CardTitle({ icon: Icon, children, aside }: { icon?: LucideIcon; children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mb-4 flex items-center justify-between gap-3">
      <h2 className="flex items-center gap-2 text-[15px] font-semibold">
        {Icon && <Icon aria-hidden className="h-4 w-4 text-muted" />}
        {children}
      </h2>
      {aside}
    </div>
  );
}

/* ---- buttons ----------------------------------------------------------------------------------------------------- */
const button = cva(
  "inline-flex items-center justify-center gap-2 rounded-[10px] font-medium transition-colors duration-fast disabled:cursor-not-allowed disabled:opacity-50",
  {
    variants: {
      variant: {
        primary: "bg-primary-strong text-white hover:bg-primary-strong/90",
        secondary: "border border-line bg-surface-2 text-fg hover:bg-surface",
        ghost: "text-muted hover:bg-white/5 hover:text-fg",
        danger: "bg-danger-strong text-white hover:bg-danger-strong/90",
      },
      size: { sm: "h-8 px-3 text-[13px]", md: "h-10 px-4 text-sm", icon: "h-9 w-9" },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);
export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof button> {
  loading?: boolean;
}
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, loading, children, disabled, ...p }, ref) => (
  <button ref={ref} className={cn(button({ variant, size }), className)} disabled={disabled || loading} aria-busy={loading || undefined} {...p}>
    {loading && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
    {children}
  </button>
));
Button.displayName = "Button";

/* ---- form fields ------------------------------------------------------------------------------------------------- */
export interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: string;
  error?: string | null;
  trailing?: ReactNode;
}
export const Field = forwardRef<HTMLInputElement, FieldProps>(({ label, hint, error, trailing, id, className, ...p }, ref) => {
  const fid = id ?? `f-${label.toLowerCase().replace(/\W+/g, "-")}`;
  const describedBy = [hint ? `${fid}-hint` : null, error ? `${fid}-err` : null].filter(Boolean).join(" ") || undefined;
  return (
    <div className="space-y-1.5">
      <label htmlFor={fid} className="block text-[13px] font-medium text-fg">
        {label}
      </label>
      <div className="relative">
        <input
          ref={ref}
          id={fid}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={cn(
            "h-10 w-full rounded-[10px] border bg-surface px-3 text-sm text-fg placeholder:text-muted/70",
            error ? "border-danger" : "border-line",
            trailing ? "pr-10" : "",
            className,
          )}
          {...p}
        />
        {trailing && <div className="absolute inset-y-0 right-1 flex items-center">{trailing}</div>}
      </div>
      {hint && !error && (
        <p id={`${fid}-hint`} className="text-[12px] text-muted">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${fid}-err`} className="text-[12px] text-danger">
          {error}
        </p>
      )}
    </div>
  );
});
Field.displayName = "Field";

/* ---- banners ----------------------------------------------------------------------------------------------------- */
const TONE_ICON: Record<string, LucideIcon> = { danger: ShieldAlert, warn: AlertTriangle, info: Info, ok: ShieldCheck };
export function Banner({ tone = "info", icon, children }: { tone?: "danger" | "warn" | "info" | "ok"; icon?: LucideIcon; children: ReactNode }) {
  const Icon = icon ?? TONE_ICON[tone] ?? Info;
  const tones = {
    danger: "border-danger/40 bg-danger/10 text-danger",
    warn: "border-warn/40 bg-warn/10 text-warn",
    info: "border-info/40 bg-info/10 text-info",
    ok: "border-ok/40 bg-ok/10 text-ok",
  } as const;
  return (
    <div role={tone === "danger" || tone === "warn" ? "alert" : "status"} className={cn("flex items-start gap-2 rounded-[10px] border px-3 py-2 text-[13px]", tones[tone])}>
      <Icon aria-hidden className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="text-fg">{children}</div>
    </div>
  );
}

/* ---- status badges: always icon + label, never color alone -------------------------------------------------------- */
export type Tone = "ok" | "warn" | "danger" | "info" | "ml" | "muted";
const TONE_CLASS: Record<Tone, string> = {
  ok: "border-ok/35 bg-ok/10 text-ok",
  warn: "border-warn/35 bg-warn/10 text-warn",
  danger: "border-danger/35 bg-danger/10 text-danger",
  info: "border-info/35 bg-info/10 text-info",
  ml: "border-ml/35 bg-ml/10 text-ml",
  muted: "border-line bg-surface-2 text-muted",
};
export function Badge({ tone = "muted", icon: Icon, children, className }: { tone?: Tone; icon?: LucideIcon; children: ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide", TONE_CLASS[tone], className)}>
      {Icon && <Icon aria-hidden className="h-3 w-3" />}
      {children}
    </span>
  );
}

/** Rule integrity statuses published by the engine (core/api/data.py RULE_STATUSES). */
export const RULE_STATUS: Record<string, { tone: Tone; icon: LucideIcon; label: string; help: string }> = {
  ok: { tone: "ok", icon: ShieldCheck, label: "Verified", help: "Matches the signed rule the controller installed." },
  altered: { tone: "danger", icon: ShieldAlert, label: "Altered", help: "Same rule slot, but what it does was changed on the switch." },
  forged: { tone: "danger", icon: ShieldAlert, label: "Forged", help: "A rule the controller never installed." },
  shadow: { tone: "danger", icon: ShieldAlert, label: "Shadow", help: "An unknown rule above a protected rule that takes over its traffic." },
  missing: { tone: "warn", icon: AlertTriangle, label: "Missing", help: "A signed rule is gone from the switch." },
  pending: { tone: "info", icon: CircleDashed, label: "Pending", help: "The engine's own change to this rule is in flight." },
};
export function RuleStatusBadge({ status }: { status: string }) {
  const s = RULE_STATUS[status] ?? { tone: "muted" as Tone, icon: Info, label: status, help: "" };
  return (
    <Badge tone={s.tone} icon={s.icon}>
      <span title={s.help}>{s.label}</span>
    </Badge>
  );
}

export const SEVERITY: Record<string, { tone: Tone; icon: LucideIcon; label: string }> = {
  critical: { tone: "danger", icon: ShieldAlert, label: "Critical" },
  high: { tone: "danger", icon: ShieldAlert, label: "High" },
  medium: { tone: "warn", icon: AlertTriangle, label: "Medium" },
  low: { tone: "info", icon: Info, label: "Low" },
  info: { tone: "info", icon: Info, label: "Info" },
};
export function SeverityBadge({ severity }: { severity: string }) {
  const s = SEVERITY[severity] ?? SEVERITY.info!;
  return (
    <Badge tone={s.tone} icon={s.icon}>
      {s.label}
    </Badge>
  );
}

export function ModeBadge({ mode }: { mode: "live" | "replay" | "simulated" }) {
  if (mode === "live")
    return (
      <Badge tone="ok">
        <span aria-hidden className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-ok" />
        Live
      </Badge>
    );
  if (mode === "replay") return <Badge tone="info">Replay</Badge>;
  return (
    <Badge tone="ml" icon={Sparkles} className="bg-[repeating-linear-gradient(135deg,transparent_0_6px,rgb(var(--ml)/0.12)_6px_12px)]">
      Simulated
    </Badge>
  );
}

/* ---- loading / empty / error states --------------------------------------------------------------------------- */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("animate-pulse rounded-md bg-fg/10", className)} />;
}
export function EmptyState({ icon: Icon = Info, title, children }: { icon?: LucideIcon; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-8 text-center">
      <Icon aria-hidden className="h-6 w-6 text-muted" />
      <p className="text-sm font-medium">{title}</p>
      {children && <div className="max-w-sm text-[13px] text-muted">{children}</div>}
    </div>
  );
}
