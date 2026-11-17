import { delays, parseSession, summarize, toFeed } from "./replay";

const line = (at: number, rec: object) => JSON.stringify({ recorded_at: at, record: rec });
const SESSION = [
  line(100, { type: "event", kind: "engine_start", t: 100 }),
  line(101.2, { type: "alert", id: "a1", kind: "forged", severity: "high", dpid: "0000000000000001", table_id: 0, priority: 300, action: "removed", t: 101.2 }),
  "not json at all",
  '{"recorded_at": "x", "record": {}}',
  line(160, { type: "alert", id: "a2", kind: "missing", severity: "medium", t: 160 }),
  '{"recorded_at": 170, "record": {"type": "ale',  // half-written last line
].join("\n");

test("a recording is parsed in time order and damaged lines are skipped, never fatal", () => {
  const e = parseSession(SESSION);
  expect(e.map((x) => x.at)).toEqual([100, 101.2, 160]);
  expect(parseSession("")).toEqual([]);
  expect(parseSession(line(5, { type: "alert" }) + "\n" + line(2, { type: "event" })).map((x) => x.at)).toEqual([2, 5]);
});

test("waits follow the recorded gaps, scale with speed, and a long quiet stretch is capped", () => {
  const e = parseSession(SESSION);
  const d = delays(e, 1);
  expect(d[0]).toBe(0);
  expect(d[1]).toBeCloseTo(1200, 3);
  expect(d[2]).toBe(1500);                                  // 58.8 s gap capped at 1.5 s
  expect(delays(e, 20)[1]).toBeCloseTo(60, 5);             // 1.2 s / 20
  expect(delays([], 5)).toEqual([]);
});

test("summary counts records and alerts by kind; alerts become feed items", () => {
  const e = parseSession(SESSION);
  expect(summarize(e)).toMatchObject({ records: 3, seconds: 60, byType: { event: 1, alert: 2 }, alertsByKind: { forged: 1, missing: 1 } });
  const f = toFeed(e[1]!)!;
  expect(f.type).toBe("alert");
  expect(f.text).toContain("forged");
});
