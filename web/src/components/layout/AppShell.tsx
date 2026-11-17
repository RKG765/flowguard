import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Toaster, toast } from "sonner";
import { Bell, LogOut, Moon, Search, Sun } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { engineFresh, useLive, type LiveEngineStatus } from "@/lib/live";
import { usePrefs } from "@/lib/prefs";
import { cn } from "@/lib/cn";
import { Badge, Button, ModeBadge } from "@/components/ui/primitives";
import { CommandPalette } from "./CommandPalette";
import { NAV } from "./nav";

function Logo() {
  return (
    <div className="flex items-center gap-2.5 px-2">
      <svg aria-hidden viewBox="0 0 32 32" className="h-8 w-8">
        <rect x="2" y="9" width="28" height="14" rx="2" fill="none" stroke="#e6ebf2" strokeWidth="1.6" />
        {["#3b82c4", "#f08a24", "#3fae5a", "#d6453d"].map((c, i) => (
          <rect key={c} x={6 + i * 6} y="13" width="4" height="6" rx="1" fill={c} />
        ))}
      </svg>
      <div>
        <div className="font-label text-[19px] font-semibold uppercase leading-5 tracking-[0.08em]">FlowGuard</div>
        <div className="text-[11.5px] text-[#a9b6c8]">SDN rule integrity</div>
      </div>
    </div>
  );
}

function Sidebar() {
  const user = useAuth((s) => s.user);
  const unseen = useLive((s) => s.unseenAlerts);
  return (
    <aside className="rail sticky top-0 hidden h-screen w-56 shrink-0 flex-col p-3 md:flex" aria-label="Main navigation">
      <Logo />
      <nav className="mt-6 flex-1 space-y-0.5 overflow-y-auto">
        {NAV.filter((n) => n.to !== "/design").map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.to === "/"}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-[3px] px-3 py-2 text-[14px] transition-colors duration-fast",
                isActive ? "bg-[#5eb0e8] font-semibold text-[#0f1d2c]" : "text-[#b4c0d0] hover:bg-white/5 hover:text-white",
              )
            }
          >
            <n.icon aria-hidden className="h-4 w-4" />
            <span className="flex-1">{n.label}</span>
            {n.to === "/alerts" && unseen > 0 && (
              <span className="tabular rounded-full bg-danger-strong px-1.5 text-[11px] font-semibold text-white" aria-label={`${unseen} new alerts`}>
                {unseen}
              </span>
            )}
          </NavLink>
        ))}
      </nav>
      {user && (
        <div className="mt-3 flex items-center gap-2 rounded-[3px] border border-white/15 bg-white/5 p-2">
          <div aria-hidden className="grid h-8 w-8 place-items-center rounded-full bg-white/15 text-[12px] font-semibold uppercase text-white">
            {user.username.slice(0, 2)}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[13px] font-medium">{user.username}</div>
            <div className="text-[11px] capitalize text-[#a9b6c8]">{user.role}</div>
          </div>
        </div>
      )}
    </aside>
  );
}

/** Narrow screens: the rail becomes a scrollable strip under the top bar. */
function MobileNav() {
  const unseen = useLive((s) => s.unseenAlerts);
  return (
    <nav aria-label="Main navigation (compact)" className="rail sticky top-14 z-10 flex gap-1 overflow-x-auto px-2 py-1.5 md:hidden">
      {NAV.filter((n) => n.to !== "/design").map((n) => (
        <NavLink
          key={n.to}
          to={n.to}
          end={n.to === "/"}
          className={({ isActive }) =>
            cn("flex shrink-0 items-center gap-1.5 rounded-[3px] px-3 py-2 text-[13px]", isActive ? "bg-[#5eb0e8] font-semibold text-[#0f1d2c]" : "text-[#b4c0d0]")
          }
        >
          <n.icon aria-hidden className="h-4 w-4" />
          {n.label}
          {n.to === "/alerts" && unseen > 0 && <span className="tabular rounded-full bg-danger-strong px-1.5 text-[11px] font-semibold text-white">{unseen}</span>}
        </NavLink>
      ))}
    </nav>
  );
}

/** Remediation mode of the engine: whether it repairs by itself or only reports. */
function ModePill() {
  const engine = useLive((s) => s.engine);
  if (!engine?.response_mode) return null;
  const auto = engine.response_mode === "restore";
  return <span className="hidden md:inline-flex"><Badge tone={auto ? "ok" : "warn"}>{auto ? "Auto-repair" : "Alert only"}</Badge></span>;
}

function LiveStatus() {
  const engine = useLive((s) => s.engine);
  const socket = useLive((s) => s.socket);
  const [now, setNow] = useState(Date.now() / 1000);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now() / 1000), 2000);
    return () => clearInterval(t);
  }, []);
  const fresh = engineFresh(engine, now);
  const monitorsUp = engine ? Object.values(engine.monitors_up).filter(Boolean).length : 0;
  const ok = socket === "open" && fresh && monitorsUp > 0;
  const text =
    socket !== "open" ? "Connecting to core…" : !engine ? "Waiting for engine status…" : !fresh ? "Engine not reporting" : monitorsUp ? `Engine connected · monitor up` : "Engine connected · monitor down";
  return (
    <div role="status" aria-live="polite" className={cn("flex items-center gap-2 whitespace-nowrap rounded-[3px] border px-3 py-1 text-[12.5px]", ok ? "border-ok/50 bg-ok/10" : "border-warn/50 bg-warn/10")}>
      <span aria-hidden className={cn("h-2 w-2 rounded-full", ok ? "animate-pulse-dot bg-ok" : "bg-warn")} />
      <span className="sr-only sm:not-sr-only">{text}</span>
    </div>
  );
}

function TopBar({ onOpenPalette }: { onOpenPalette: () => void }) {
  const { theme, toggleTheme } = usePrefs();
  const logout = useAuth((s) => s.logout);
  const navigate = useNavigate();
  const loc = useLocation();
  const title = NAV.find((n) => (n.to === "/" ? loc.pathname === "/" : loc.pathname.startsWith(n.to)))?.label ?? "FlowGuard";
  const unseen = useLive((s) => s.unseenAlerts);
  const markSeen = useLive((s) => s.markSeen);
  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-2 border-b border-line bg-surface px-3 sm:gap-3 sm:px-5">
      <h1 className="label shrink-0 whitespace-nowrap !text-[19px] !text-fg sm:!text-[22px]">{title}</h1>
      <button
        onClick={onOpenPalette}
        className="ml-4 hidden h-9 w-64 min-w-0 shrink items-center gap-2 sm:flex overflow-hidden whitespace-nowrap rounded-[3px] border border-line bg-surface/70 px-3 text-left text-[13px] text-muted hover:text-fg"
        aria-label="Open command palette (Ctrl+K)"
      >
        <Search aria-hidden className="h-4 w-4" />
        <span className="flex-1 truncate">Search pages…</span>
        <kbd className="rounded border border-line px-1.5 text-[11px]">Ctrl K</kbd>
      </button>
      <div className="ml-auto flex items-center gap-2">
        <LiveStatus />
        <ModePill />
        <span className="hidden md:inline-flex"><ModeBadge mode="live" /></span>
        <span className="hidden md:inline-flex"><Badge tone="muted">WSL2</Badge></span>
        <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}>
          {theme === "dark" ? <Sun aria-hidden className="h-4 w-4" /> : <Moon aria-hidden className="h-4 w-4" />}
        </Button>
        <Button
          variant="ghost"
          size="icon"
          aria-label={unseen ? `${unseen} new alerts` : "Alerts"}
          onClick={() => {
            markSeen();
            navigate("/alerts");
          }}
          className="relative"
        >
          <Bell aria-hidden className="h-4 w-4" />
          {unseen > 0 && <span aria-hidden className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-danger" />}
        </Button>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Sign out"
          onClick={async () => {
            await logout();
            navigate("/login");
          }}
        >
          <LogOut aria-hidden className="h-4 w-4" />
        </Button>
      </div>
    </header>
  );
}

export function AppShell() {
  const [palette, setPalette] = useState(false);
  const prefsTheme = usePrefs((s) => s.theme);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const connect = useLive((s) => s.connect);
  const disconnect = useLive((s) => s.disconnect);

  useEffect(() => {
    useLive.setState({
      onInvalidate: (what) => void qc.invalidateQueries({ queryKey: [what] }),
      onAlert: (item) =>
        toast.error(item.text, {
          description: "Click to open the alert",
          action: { label: "Open", onClick: () => navigate(`/alerts?id=${encodeURIComponent(item.alertId ?? "")}`) },
        }),
    });
    connect();
    // the engine pushes its status every 5 s; seed it now so the top bar is right immediately after a reload
    void api<{ known: boolean; status?: LiveEngineStatus }>("/api/engine/status")
      .then((r) => {
        if (r.known && r.status && !useLive.getState().engine) useLive.setState({ engine: r.status });
      })
      .catch(() => undefined);
    return () => disconnect();
  }, [qc, navigate, connect, disconnect]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((p) => !p);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="flex min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-primary-strong focus:px-3 focus:py-2 focus:text-white">
        Skip to content
      </a>
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onOpenPalette={() => setPalette(true)} />
        <MobileNav />
        <main id="main" className="min-w-0 flex-1 overflow-x-auto p-3 sm:p-5" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
      <CommandPalette open={palette} onOpenChange={setPalette} />
      <Toaster theme={prefsTheme} position="bottom-right" closeButton toastOptions={{ classNames: { toast: "!rounded-[3px] !border !border-line !bg-surface !text-fg !shadow-none", description: "!text-muted", closeButton: "!border-line !bg-surface !text-fg" } }} />
    </div>
  );
}
