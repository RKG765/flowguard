import { useLocation } from "react-router-dom";
import { Construction } from "lucide-react";
import { NAV } from "@/components/layout/nav";
import { EmptyState, GlassCard } from "@/components/ui/primitives";

/** Honest placeholder for pages that are planned but not built (CLAUDE.md rule 3: never present unbuilt features). */
export function Planned() {
  const loc = useLocation();
  const item = NAV.find((n) => n.to !== "/" && loc.pathname.startsWith(n.to));
  return (
    <GlassCard>
      <EmptyState icon={Construction} title={`${item?.label ?? "This page"} is planned`}>
        It arrives in Phase {item?.phase ?? "?"} of the build plan. The data it will show is already collected by the engine and stored by the core
        where that applies; see STATUS.md for what exists today.
      </EmptyState>
    </GlassCard>
  );
}

export function NotFound() {
  return (
    <GlassCard>
      <EmptyState title="Page not found">Use the sidebar or Ctrl+K to find a page.</EmptyState>
    </GlassCard>
  );
}
