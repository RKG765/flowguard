import { useState } from "react";
import { toast } from "sonner";
import { Wrench } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { hasRole, useAuth } from "@/lib/auth";
import type { Match } from "@/lib/format";
import { formatMatch } from "@/lib/format";
import { Button } from "@/components/ui/primitives";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

export interface RepairTarget {
  dpid: string;
  table_id: number;
  priority: number;
  match: Match;
  status: string;
}

const WHAT: Record<string, string> = {
  altered: "replace the changed rule on the switch with the version the controller signed",
  missing: "re-install the signed rule that is missing from the switch",
  forged: "remove the rule, because the controller never installed it",
  shadow: "remove the rule that sits above a protected rule and takes over its traffic",
};

/** Admin-only, confirmed, audited (by the core). Hidden for other roles and for rules that need no repair. */
export function RepairButton({ target, onDone }: { target: RepairTarget; onDone?: () => void }) {
  const user = useAuth((s) => s.user);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  if (!hasRole(user, "admin") || !(target.status in WHAT)) return null;
  async function run() {
    setBusy(true);
    try {
      await api("/api/rules/repair", { method: "POST", body: { dpid: target.dpid, table_id: target.table_id, priority: target.priority, match: target.match } });
      toast.success("Repair requested", { description: "The engine applies it on its next check, usually within a second." });
      setOpen(false);
      onDone?.();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.detail : "Could not request the repair");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Button variant="danger" size="sm" onClick={() => setOpen(true)}>
        <Wrench aria-hidden className="h-4 w-4" />
        Repair this rule
      </Button>
      <ConfirmDialog open={open} onOpenChange={setOpen} title="Repair this rule?" confirmLabel="Repair now" onConfirm={run} busy={busy} tone="danger">
        <p>FlowGuard will {WHAT[target.status]}.</p>
        <p className="mono text-fg">switch {target.dpid} · table {target.table_id} · priority {target.priority} · {formatMatch(target.match)}</p>
        <p>This is recorded in the audit log under your name.</p>
      </ConfirmDialog>
    </>
  );
}
