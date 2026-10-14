import { useEffect, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Loader2, PlugZap } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { AppShell } from "@/components/layout/AppShell";
import { NAV } from "@/components/layout/nav";
import { Button, EmptyState, GlassCard } from "@/components/ui/primitives";
import { LoginScreen, SetupScreen } from "@/pages/AuthScreen";
import { DesignGallery } from "@/pages/DesignGallery";
import { Overview } from "@/pages/Overview";
import { NotFound, Planned } from "@/pages/Planned";

function Centered({ children }: { children: ReactNode }) {
  return <main className="grid min-h-screen place-items-center p-4">{children}</main>;
}

/** Routes depend on the auth status: first-run setup, sign-in, or the app. */
function Gate({ children }: { children: ReactNode }) {
  const status = useAuth((s) => s.status);
  const bootstrap = useAuth((s) => s.bootstrap);
  const loc = useLocation();
  if (status === "loading")
    return (
      <Centered>
        <Loader2 aria-label="Loading" className="h-6 w-6 animate-spin text-muted" />
      </Centered>
    );
  if (status === "offline")
    return (
      <Centered>
        <GlassCard className="max-w-md">
          <EmptyState icon={PlugZap} title="The FlowGuard core is not reachable">
            Start it with <span className="mono">make run-core</span>, then retry.
          </EmptyState>
          <div className="flex justify-center">
            <Button onClick={() => void bootstrap()}>Retry</Button>
          </div>
        </GlassCard>
      </Centered>
    );
  if (status === "needs-setup" && loc.pathname !== "/setup") return <Navigate to="/setup" replace />;
  if (status === "anonymous" && loc.pathname !== "/login") return <Navigate to="/login" replace />;
  if (status === "authenticated" && (loc.pathname === "/login" || loc.pathname === "/setup")) return <Navigate to="/" replace />;
  return <>{children}</>;
}

export default function App() {
  const bootstrap = useAuth((s) => s.bootstrap);
  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);
  return (
    <Gate>
      <Routes>
        <Route path="/setup" element={<SetupScreen />} />
        <Route path="/login" element={<LoginScreen />} />
        <Route element={<AppShell />}>
          <Route index element={<Overview />} />
          <Route path="design" element={<DesignGallery />} />
          {NAV.filter((n) => n.phase > 3).map((n) => (
            <Route key={n.to} path={n.to.slice(1)} element={<Planned />} />
          ))}
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Gate>
  );
}
