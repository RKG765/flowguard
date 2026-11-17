import { describe, type FeedItem } from "./live";

/** One line of a recorded session as the core writes it: {"recorded_at": seconds, "record": {...the engine record...}}. */
export interface Entry {
  at: number;
  rec: Record<string, unknown>;
}

/** Parse a recorded session (NDJSON). Damaged lines are skipped, never fatal; entries come back in time order. */
export function parseSession(text: string): Entry[] {
  const out: Entry[] = [];
  for (const line of text.split("\n")) {
    if (!line.trim()) continue;
    try {
      const j = JSON.parse(line) as { recorded_at?: unknown; record?: unknown };
      if (typeof j.recorded_at === "number" && j.record && typeof j.record === "object") out.push({ at: j.recorded_at, rec: j.record as Record<string, unknown> });
    } catch {
      /* a half-written last line or a damaged line: skip it */
    }
  }
  return out.sort((a, b) => a.at - b.at);
}

/** Wait before each entry, in ms: the recorded gap divided by the speed, capped so a long quiet stretch does not stall the replay. */
export function delays(entries: Entry[], speed: number, maxGapMs = 1500): number[] {
  return entries.map((e, i) => (i === 0 ? 0 : Math.min(maxGapMs, Math.max(0, ((e.at - entries[i - 1]!.at) * 1000) / speed))));
}

export const toFeed = (e: Entry): FeedItem | null => describe({ type: String(e.rec.type ?? "event"), data: e.rec });

/** Counts for the header of a replay: records by type and alerts by kind. */
export function summarize(entries: Entry[]): { records: number; seconds: number; byType: Record<string, number>; alertsByKind: Record<string, number> } {
  const byType: Record<string, number> = {};
  const alertsByKind: Record<string, number> = {};
  for (const e of entries) {
    const t = String(e.rec.type ?? "event");
    byType[t] = (byType[t] ?? 0) + 1;
    if (t === "alert") {
      const k = String(e.rec.kind ?? "alert");
      alertsByKind[k] = (alertsByKind[k] ?? 0) + 1;
    }
  }
  return { records: entries.length, seconds: entries.length ? Math.round(entries[entries.length - 1]!.at - entries[0]!.at) : 0, byType, alertsByKind };
}
