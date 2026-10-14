import { Command } from "cmdk";
import * as Dialog from "@radix-ui/react-dialog";
import { useNavigate } from "react-router-dom";
import { Eye, LogOut, Moon, Search, Wind } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { usePrefs } from "@/lib/prefs";
import { NAV } from "./nav";

/** Ctrl+K: jump to pages and run display actions. Searching rules/alerts and running attacks arrive with those pages
 *  (Phase 4); the palette lists only what exists. */
export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const navigate = useNavigate();
  const prefs = usePrefs();
  const logout = useAuth((s) => s.logout);
  const run = (fn: () => void) => {
    onOpenChange(false);
    fn();
  };
  const item = "flex cursor-pointer items-center gap-3 rounded-[8px] px-3 py-2 text-[13.5px] aria-selected:bg-primary/15";
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40" />
        <Dialog.Content className="glass fixed left-1/2 top-[18%] z-50 w-[560px] -translate-x-1/2 p-2" aria-describedby={undefined}>
          <Dialog.Title className="sr-only">Command palette</Dialog.Title>
          <Command label="Command palette" loop>
            <div className="flex items-center gap-2 border-b border-line px-3 pb-2">
              <Search aria-hidden className="h-4 w-4 text-muted" />
              <Command.Input autoFocus placeholder="Type a page or an action…" className="h-9 w-full bg-transparent text-sm outline-none placeholder:text-muted" />
            </div>
            <Command.List className="max-h-[360px] overflow-y-auto p-1">
              <Command.Empty className="px-3 py-6 text-center text-sm text-muted">Nothing matches.</Command.Empty>
              <Command.Group heading="Go to" className="px-1 py-1 text-[11px] text-muted [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pb-1">
                {NAV.map((n) => (
                  <Command.Item key={n.to} value={`${n.label} ${n.keywords ?? ""}`} onSelect={() => run(() => navigate(n.to))} className={item}>
                    <n.icon aria-hidden className="h-4 w-4 text-muted" />
                    <span className="flex-1 text-fg">{n.label}</span>
                    {n.phase > 3 && <span className="text-[11px] text-muted">planned · Phase {n.phase}</span>}
                  </Command.Item>
                ))}
              </Command.Group>
              <Command.Group heading="Display" className="px-1 py-1 text-[11px] text-muted [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pb-1">
                <Command.Item value="toggle theme dark light" onSelect={() => run(prefs.toggleTheme)} className={item}>
                  <Moon aria-hidden className="h-4 w-4 text-muted" />
                  <span className="text-fg">Switch to {prefs.theme === "dark" ? "light" : "dark"} theme</span>
                </Command.Item>
                <Command.Item value="reduce motion animation" onSelect={() => run(() => prefs.setReducedMotion(!prefs.reducedMotion))} className={item}>
                  <Wind aria-hidden className="h-4 w-4 text-muted" />
                  <span className="text-fg">{prefs.reducedMotion ? "Allow motion" : "Reduce motion"}</span>
                </Command.Item>
                <Command.Item value="reduce transparency glass solid" onSelect={() => run(() => prefs.setReducedTransparency(!prefs.reducedTransparency))} className={item}>
                  <Eye aria-hidden className="h-4 w-4 text-muted" />
                  <span className="text-fg">{prefs.reducedTransparency ? "Allow transparency" : "Reduce transparency (solid surfaces)"}</span>
                </Command.Item>
              </Command.Group>
              <Command.Group heading="Session" className="px-1 py-1 text-[11px] text-muted [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pb-1">
                <Command.Item value="sign out logout" onSelect={() => run(async () => { await logout(); navigate("/login"); })} className={item}>
                  <LogOut aria-hidden className="h-4 w-4 text-muted" />
                  <span className="text-fg">Sign out</span>
                </Command.Item>
              </Command.Group>
            </Command.List>
          </Command>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
