import { CheckCircle2, CircleDashed } from "lucide-react";
import { fmtTime } from "@/lib/cn";
import type { AlertFull } from "@/lib/types";
import { RuleDiff } from "@/components/rules/RuleDiff";
import { Badge, SeverityBadge } from "@/components/ui/primitives";

const ACTION_TEXT: Record<string, string> = {
  restored: "FlowGuard re-installed the rule the controller signed.",
  removed: "FlowGuard removed the rule from the switch.",
  none: "FlowGuard did not change the switch.",
};
const REASON_TEXT: Record<string, string> = {
  instructions_differ: "what the rule does differs from the signed version",
  cookie_differs: "its signature (cookie) is not the one the controller issued",
  rule_absent: "the signed rule is no longer on the switch",
  not_in_golden_store: "the controller never installed this rule",
};
const DETECTED_BY: Record<string, string> = {
  monitor_event: "a live change notification from the switch",
  reconcile_poll: "the periodic safety check of the rule table",
  manual_repair: "a repair requested from the dashboard",
  startup: "the check made when the switch connected",
  confirm: "the follow-up check after a repair",
  attributed_check: "a re-check after one of FlowGuard's own changes",
  monitor_up: "the check made when the change monitor reconnected",
};

function Step({ label, t, ms, done }: { label: string; t?: number | null; ms?: number | null; done: boolean }) {
  return (
    <li className="flex items-start gap-2.5">
      {done ? <CheckCircle2 aria-hidden className="mt-0.5 h-4 w-4 text-ok" /> : <CircleDashed aria-hidden className="mt-0.5 h-4 w-4 text-muted" />}
      <div className="flex-1">
        <div className="text-[13px]">{label}</div>
        <div className="mono text-muted">{t ? fmtTime(t) : "—"}{ms !== undefined && ms !== null ? ` · +${ms.toFixed(1)} ms` : ""}</div>
      </div>
    </li>
  );
}

/** "What happened, why we think so, what we did" in plain language, plus the measured timeline and the rule diff. */
export function AlertExplain({ a }: { a: AlertFull }) {
  const d = a.details ?? {};
  const tm = d.timing ?? {};
  const reasons = (d.reasons ?? []).map((r) => REASON_TEXT[r] ?? r.replace(/_/g, " "));
  const action = a.action ?? "none";
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge severity={a.severity} />
        <Badge tone="info">Layer {a.layer}</Badge>
        <Badge tone="muted">{a.kind.replace(/_/g, " ")}</Badge>
      </div>
      <section>
        <h3 className="text-[13px] font-semibold">What happened</h3>
        <p className="mt-1 text-[13.5px]">{a.summary ?? "No description."}</p>
      </section>
      <section>
        <h3 className="text-[13px] font-semibold">Why FlowGuard thinks so</h3>
        <ul className="mt-1 list-disc space-y-0.5 pl-5 text-[13.5px] text-muted">
          {reasons.map((r) => <li key={r}>{r}</li>)}
          {d.signature_valid === false && <li>the rule's signature does not verify with the controller's key</li>}
          {d.signature_valid === true && <li>the rule carries a valid signature but is not in the controller's current rule set (replayed or stale)</li>}
          {d.shadows && d.shadows.length > 0 && <li>it takes traffic away from: {d.shadows.join("; ")}</li>}
          {a.detected_by && <li>noticed through {DETECTED_BY[a.detected_by] ?? a.detected_by}</li>}
          {d.events && d.events.length > 0 && <li>{d.events.length} change notification(s) from the switch that the controller did not cause</li>}
        </ul>
      </section>
      <section>
        <h3 className="text-[13px] font-semibold">What FlowGuard did</h3>
        <p className="mt-1 text-[13.5px]">{ACTION_TEXT[action] ?? action}{d.action_reason === "rate_limited" ? " Automatic repairs were paused by the rate limit on this switch." : ""}{d.action_reason === "alert_only" ? " The engine runs in alert-only mode; an admin can repair the rule from the Rules page." : ""}</p>
      </section>
      <section>
        <h3 className="text-[13px] font-semibold">Timeline (engine clock)</h3>
        <ol className="mt-2 space-y-2">
          <Step label="Change reported by the switch" t={tm.t_event_rx} done={!!tm.t_event_rx} />
          <Step label="Rule table read and classified" t={tm.t_classified} ms={a.detect_latency_ms} done={!!tm.t_classified} />
          <Step label="Repair sent to the switch" t={tm.t_response_sent} ms={tm.respond_latency_ms ?? null} done={!!tm.t_response_sent} />
          <Step label="Switch confirmed the repair" t={a.restored_at} ms={a.time_to_restore_ms} done={!!a.restored_at} />
        </ol>
      </section>
      {(d.observed || d.golden) && (
        <section>
          <h3 className="mb-2 text-[13px] font-semibold">Rule before the repair</h3>
          <RuleDiff signed={d.golden?.instructions ?? null} observed={d.observed?.instructions ?? null}
                    signedCookie={d.golden?.cookie} observedCookie={d.observed?.cookie} present={!!d.observed} />
        </section>
      )}
    </div>
  );
}
