import { freshRules, repairAll, tamper } from "./demo";

const run = (kind: Parameters<typeof tamper>[1]) => tamper(freshRules(), kind, "s2-r1", 1, () => 0.5);

test("every tampering kind makes a rule non-ok and repairAll restores the signed policy exactly", () => {
  for (const kind of ["altered", "forged", "missing", "shadow", "unattributed_change"] as const) {
    const { rules, event } = run(kind);
    expect(rules.some((r) => r.status !== "ok")).toBe(true);
    expect(event.detectMs).toBeGreaterThanOrEqual(6);
    expect(repairAll(rules)).toEqual(freshRules());
  }
});

test("altered changes the cookie, missing removes the rule, forged adds one unsigned rule", () => {
  const a = run("altered").event;
  expect(a.foundCookie).not.toBe(a.signedCookie);
  expect(run("missing").event.found).toBeNull();
  const f = run("forged");
  expect(f.rules.length).toBe(freshRules().length + 1);
  expect(f.event.signed).toBeNull();
});
