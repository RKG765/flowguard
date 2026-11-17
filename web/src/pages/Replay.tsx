import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Circle, Download, Pause, Play, RotateCcw, Square, Video } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtAgo, fmtTime } from "@/lib/cn";
import { delays, parseSession, summarize, toFeed, type Entry } from "@/lib/replay";
import { Badge, Button, CardTitle, EmptyState, Field, GlassCard, ModeBadge, SeverityBadge } from "@/components/ui/primitives";

interface Session { id: string; name: string; started_at: number; stopped_at: number | null; records: number; recording: boolean }
const SEL = "h-9 rounded-[3px] border border-line bg-surface px-2 text-sm text-fg";
const err = (e: unknown) => (e instanceof ApiError ? e.detail : "Could not reach the core.");

/** Record what the engine reports (admin), download it, and replay it later in this page: no lab, no engine, no server state. */
export function ReplayCard() {
  const qc = useQueryClient();
  const role = useAuth((s) => s.user)?.role ?? "viewer";
  const [name, setName] = useState("demo session");
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: () => api<Session[]>("/api/sessions"), refetchInterval: 5000 });
  const start = useMutation({
    mutationFn: () => api<Session>("/api/sessions", { method: "POST", body: { name } }),
    onSuccess: () => { toast.success("Recording started"); void qc.invalidateQueries({ queryKey: ["sessions"] }); },
    onError: (e) => toast.error(err(e)),
  });
  const stop = useMutation({
    mutationFn: (id: string) => api<Session>(`/api/sessions/${id}/stop`, { method: "POST" }),
    onSuccess: () => { toast.success("Recording stopped"); void qc.invalidateQueries({ queryKey: ["sessions"] }); },
    onError: (e) => toast.error(err(e)),
  });

  const [run, setRun] = useState<{ name: string; entries: Entry[] } | null>(null);
  const [pos, setPos] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(5);
  const [loading, setLoading] = useState<string | null>(null);

  useEffect(() => {
    if (!run || !playing) return;
    if (pos >= run.entries.length) {
      setPlaying(false);
      return;
    }
    const t = setTimeout(() => setPos((p) => p + 1), delays(run.entries, speed)[pos]);
    return () => clearTimeout(t);
  }, [run, playing, pos, speed]);

  async function load(s: Session) {
    setLoading(s.id);
    try {
      const res = await fetch(`/api/sessions/${encodeURIComponent(s.id)}/download`, { credentials: "same-origin" });
      if (!res.ok) throw new Error(String(res.status));
      const entries = parseSession(await res.text());
      if (!entries.length) toast.info("This recording has no records yet");
      setRun({ name: s.name, entries });
      setPos(0);
      setPlaying(entries.length > 0);
    } catch {
      toast.error("Could not load the recording (analyst role needed)");
    } finally {
      setLoading(null);
    }
  }

  const seen = run ? run.entries.slice(0, pos) : [];
  const feed = seen.map(toFeed).filter((f): f is NonNullable<ReturnType<typeof toFeed>> => f !== null).reverse().slice(0, 25);
  const sum = summarize(seen);
  const total = run ? summarize(run.entries) : null;

  return (
    <GlassCard>
      <CardTitle icon={Video} aside={run ? <ModeBadge mode="replay" /> : undefined}>Recorded sessions and replay</CardTitle>
      {role === "admin" && (
        <form className="mb-4 flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); start.mutate(); }}>
          <div className="w-64"><Field label="New recording" value={name} onChange={(e) => setName(e.target.value)} /></div>
          <Button type="submit" size="sm" loading={start.isPending} disabled={!name.trim() || !!sessions.data?.some((s) => s.recording)}><Circle aria-hidden className="h-3.5 w-3.5" /> Record</Button>
        </form>
      )}
      {!sessions.data?.length ? (
        <EmptyState icon={Video} title="No recordings yet">An admin starts a recording; everything the engine reports while it runs is saved and can be replayed here at any speed.</EmptyState>
      ) : (
        <ul className="space-y-2">
          {sessions.data.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center gap-3 border-t border-line pt-2 text-[13px] first:border-t-0 first:pt-0">
              <strong>{s.name}</strong>
              {s.recording ? <Badge tone="danger">Recording</Badge> : <span className="text-muted">{s.records} records</span>}
              <span className="text-muted">started {fmtAgo(s.started_at)}</span>
              <span className="ml-auto flex gap-2">
                {s.recording && role === "admin" && <Button size="sm" variant="secondary" onClick={() => stop.mutate(s.id)} loading={stop.isPending}><Square aria-hidden className="h-3.5 w-3.5" /> Stop</Button>}
                {!s.recording && role !== "viewer" && <Button size="sm" onClick={() => void load(s)} loading={loading === s.id}><Play aria-hidden className="h-3.5 w-3.5" /> Replay</Button>}
                {role !== "viewer" && <a href={`/api/sessions/${s.id}/download`} download><Button size="sm" variant="secondary"><Download aria-hidden className="h-3.5 w-3.5" /> JSONL</Button></a>}
              </span>
            </li>
          ))}
        </ul>
      )}

      {run && total && (
        <div className="mt-4 border-t border-line pt-3" aria-label={`Replay of ${run.name}`}>
          <div className="flex flex-wrap items-center gap-3">
            <strong className="text-[13.5px]">{run.name}</strong>
            <span className="mono text-muted" aria-live="polite">{pos} / {run.entries.length} records · {total.seconds} s recorded</span>
            <span className="ml-auto flex items-center gap-2">
              <label className="text-[12px] text-muted">Speed
                <select className={`${SEL} ml-2`} value={speed} onChange={(e) => setSpeed(Number(e.target.value))}><option value={1}>1x</option><option value={5}>5x</option><option value={20}>20x</option><option value={100}>100x</option></select>
              </label>
              <Button size="sm" variant="secondary" onClick={() => setPlaying((p) => !p)} disabled={pos >= run.entries.length}>{playing ? <><Pause aria-hidden className="h-3.5 w-3.5" /> Pause</> : <><Play aria-hidden className="h-3.5 w-3.5" /> Play</>}</Button>
              <Button size="sm" variant="secondary" onClick={() => { setPos(0); setPlaying(true); }}><RotateCcw aria-hidden className="h-3.5 w-3.5" /> Restart</Button>
            </span>
          </div>
          <div className="mt-2 h-1.5 w-full bg-surface-2" role="progressbar" aria-valuemin={0} aria-valuemax={run.entries.length} aria-valuenow={pos}>
            <div className="h-1.5 bg-primary-strong" style={{ width: `${run.entries.length ? (pos / run.entries.length) * 100 : 0}%` }} />
          </div>
          <p className="mt-2 text-[12.5px] text-muted">
            So far: {Object.keys(sum.alertsByKind).length ? Object.entries(sum.alertsByKind).map(([k, n]) => `${n} ${k.replace(/_/g, " ")}`).join(", ") : "no alerts yet"}. This is a recording: nothing here is live.
          </p>
          <ol className="mt-3 space-y-2" aria-label="Replayed events">
            {feed.map((f) => (
              <li key={f.key} className="flex items-start gap-2.5 text-[13px]">
                <span className="mono w-[92px] shrink-0 whitespace-nowrap text-muted">{fmtTime(f.t)}</span>
                <SeverityBadge severity={f.severity} />
                <span className="min-w-0 flex-1">{f.text}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </GlassCard>
  );
}
