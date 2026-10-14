import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Clock, Eye, EyeOff, Info } from "lucide-react";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Banner, Button, Field, GlassCard } from "@/components/ui/primitives";

const USERNAME_RE = /^[A-Za-z0-9_.-]{3,64}$/;

function Brand() {
  return (
    <div className="mb-6 flex flex-col items-center text-center">
      <svg aria-hidden viewBox="0 0 32 32" className="mb-3 h-11 w-11">
        <path d="M16 2 4 7v8c0 7.5 5.1 13.4 12 15 6.9-1.6 12-7.5 12-15V7L16 2Z" fill="rgb(var(--primary) / 0.18)" stroke="rgb(var(--primary))" strokeWidth="1.6" />
        <path d="M9 13h6l2 3h6M9 19h4l2-3" fill="none" stroke="rgb(var(--ok))" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
      <div className="text-xl font-semibold">FlowGuard</div>
      <div className="text-[13px] text-muted">SDN flow-rule integrity monitoring</div>
    </div>
  );
}

function PasswordField(props: { label: string; value: string; onChange: (v: string) => void; hint?: string; error?: string | null; autoComplete: string }) {
  const [show, setShow] = useState(false);
  return (
    <Field
      label={props.label}
      type={show ? "text" : "password"}
      value={props.value}
      onChange={(e) => props.onChange(e.target.value)}
      hint={props.hint}
      error={props.error}
      autoComplete={props.autoComplete}
      required
      trailing={
        <Button type="button" variant="ghost" size="icon" className="h-8 w-8" onClick={() => setShow((s) => !s)} aria-label={show ? "Hide password" : "Show password"}>
          {show ? <EyeOff aria-hidden className="h-4 w-4" /> : <Eye aria-hidden className="h-4 w-4" />}
        </Button>
      }
    />
  );
}

/** First run: creates the only bootstrap admin (the core refuses this once any user exists). */
export function SetupScreen() {
  const setup = useAuth((s) => s.setup);
  const navigate = useNavigate();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const userErr = username && !USERNAME_RE.test(username) ? "3-64 letters, digits, dot, dash or underscore" : null;
  const pwErr = password && password.length < 8 ? "At least 8 characters" : password && password.toLowerCase() === username.toLowerCase() ? "Must not be the same as the username" : null;
  const confirmErr = confirm && confirm !== password ? "Passwords do not match" : null;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (userErr || pwErr || confirmErr || !password) return;
    setBusy(true);
    setError(null);
    try {
      await setup(username, password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not reach the FlowGuard core. Is it running?");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center p-4">
      <GlassCard className="w-full max-w-[440px] p-7">
        <Brand />
        <h1 className="text-[17px] font-semibold">Create the first admin account</h1>
        <p className="mb-5 mt-1 text-[13px] text-muted">
          No users exist yet. The first account you create becomes the administrator. You can add analysts and viewers later.
        </p>
        <form className="space-y-4" onSubmit={submit} noValidate>
          {error && <Banner tone="danger">{error}</Banner>}
          <Field label="Username" value={username} onChange={(e) => setUsername(e.target.value)} hint="3-64 letters, digits, . _ -" error={userErr} autoComplete="username" required />
          <PasswordField label="Password" value={password} onChange={setPassword} hint="At least 8 characters, not the same as the username" error={pwErr} autoComplete="new-password" />
          <PasswordField label="Confirm password" value={confirm} onChange={setConfirm} error={confirmErr} autoComplete="new-password" />
          <Button type="submit" className="w-full" loading={busy} disabled={!!(userErr || pwErr || confirmErr) || !password || !confirm}>
            Create admin and continue
          </Button>
          <Banner tone="info" icon={Info}>
            This runs only on this machine (127.0.0.1).
          </Banner>
        </form>
      </GlassCard>
    </main>
  );
}

export function LoginScreen() {
  const login = useAuth((s) => s.login);
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lockedFor, setLockedFor] = useState(0);

  useEffect(() => {
    if (lockedFor <= 0) return;
    const t = setTimeout(() => setLockedFor((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [lockedFor]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
      navigate("/", { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) setLockedFor(err.retryAfter ?? 60);
      else if (err instanceof ApiError && err.status === 401) setError("Invalid username or password.");
      else if (err instanceof ApiError && err.status === 422) setError("Enter a valid username and a password.");
      else setError("Could not reach the FlowGuard core. Is it running?");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center p-4">
      <GlassCard className="w-full max-w-[440px] p-7">
        <Brand />
        <h1 className="mb-5 text-[17px] font-semibold">Sign in</h1>
        <form className="space-y-4" onSubmit={submit} noValidate>
          {error && <Banner tone="danger">{error}</Banner>}
          {lockedFor > 0 && (
            <Banner tone="warn" icon={Clock}>
              Too many failed attempts. Try again in {lockedFor} s.
            </Banner>
          )}
          <Field label="Username" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
          <PasswordField label="Password" value={password} onChange={setPassword} autoComplete="current-password" />
          <Button type="submit" className="w-full" loading={busy} disabled={!username || !password || lockedFor > 0}>
            Sign in
          </Button>
        </form>
      </GlassCard>
    </main>
  );
}
