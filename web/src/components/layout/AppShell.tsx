import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Toaster, toast } from "sonner";
import { Bell, LogOut, Moon, Search, Sun } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { engineFresh, useLive } from "@/lib/live";
import { usePrefs } from "@/lib/prefs";
import { cn } from "@/lib/cn";
import { Badge, Button, ModeBadge } from "@/components/ui/primitives";
import { CommandPalette } from "./CommandPalette";
import { NAV } from "./nav";

function Logo() {
  return (
    <div className="flex items-center gap-2.5 px-2">
      <svg aria-hidden viewBox="0 0 32 32" className="h-8 w-8">
        <path d="M16 2 4 7v8c0 7.5 5.1 13.4 12 15 6.9-1.6 12-7.5 12-15V7L16 2Z" fill="rgb(var(--primary) / 0.18)" stroke="rgb(var(--primary))" strokeWidth="1.6" />
        <path d="M9 13h6l2 3h6M9 19h4l2-3" fill="none" stroke="rgb(var(--ok))" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
      <div>
        <div className="text-[15px] font-semibold leading-5">FlowGuard</div>
        <div className="text-[11px] text-muted">SDN rule integrity</div>
      </div>
    </div>
  );
}

function Sidebar() {
  const user = useAuth((s) => s.user);
  const unseen = useLive((s) => s.unseenAlerts);
  return (
    <aside className="glass sticky top-3 m-3 flex h-[calc(100vh-24px)] w-60 shrink-0 flex-col p-3" aria-label="Main navigation">
      <Logo />
      <nav className="mt-6 flex-1 space-y-0.5 overflow-y-auto">
        {NAV.filter((n) => n.to !== "/design").map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.to === "/"}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-[10px] px-3 py-2 text-[13.5px] transition-colors duration-fast",
                isActive ? "bg-primary/15 font-medium text-fg" : "text-muted hover:bg-white/5 hover:text-fg",
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
        <div className="mt-3 flex items-center gap-2 rounded-[12px] border border-line bg-surface/60 p-2">
          <div aria-hidden className="grid h-8 w-8 place-items-center rounded-full bg-primary/20 text-[12px] font-semibold uppercase">
            {user.username.slice(0, 2)}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[13px] font-medium">{user.username}</div>
            <div className="text-[11px] capitalize text-muted">{user.role}</div>
          </div>
        </div>
      )}
    </aside>
  );
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
    <div role="status" aria-live="polite" className={cn("flex items-center gap-2 rounded-full border px-3 py-1 text-[12px]", ok ? "border-ok/35 bg-ok/10" : "border-warn/35 bg-warn/10")}>
      <span aria-hidden className={cn("h-2 w-2 rounded-full", ok ? "animate-pulse-dot bg-ok" : "bg-warn")} />
      <span>{text}</span>
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
    <header className="glass sticky top-3 z-20 mr-3 mt-3 flex h-14 items-center gap-3 px-4">
      <h1 className="text-[17px] font-semibold">{title}</h1>
      <button
        onClick={onOpenPalette}
        className="ml-4 flex h-9 w-72 items-center gap-2 rounded-[10px] border border-line bg-surface/70 px-3 text-left text-[13px] text-muted hover:text-fg"
        aria-label="Open command palette (Ctrl+K)"
      >
        <Search aria-hidden className="h-4 w-4" />
        <span className="flex-1">Search pages and actions…</span>
        <kbd className="rounded border border-line px-1.5 text-[11px]">Ctrl K</kbd>
      </button>
      <div className="ml-auto flex items-center gap-2">
        <LiveStatus />
        <ModeBadge mode="live" />
        <Badge tone="muted">WSL2</Badge>
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
        <main id="main" className="flex-1 py-5 pr-3" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
      <CommandPalette open={palette} onOpenChange={setPalette} />
      <Toaster theme={usePrefs.getState().theme} position="bottom-right" richColors closeButton />
    </div>
  );
}
