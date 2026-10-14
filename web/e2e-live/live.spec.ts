import { execFileSync } from "node:child_process";
import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/** Dashboard against the real engine (alert-only mode) on a throw-away Mininet lab. The one change made to the switch
 *  is the same unsigned-rule case as tests/integration/test_l1_live.py::test_a1 (the engine must report it). */
test.describe.configure({ mode: "serial" });

const ADMIN = { username: "admin", password: "e2e-live-admin-1" };
const IMG = "../docs/img";

async function axe(page: Page) {
  const r = await new AxeBuilder({ page: page as never }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const serious = r.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(serious.flatMap((v) => v.nodes.slice(0, 10).map((n) => `${v.id} | ${n.target.join(" ")}`))).toEqual([]);
}

async function signIn(page: Page) {
  const r = await page.request.post("/api/auth/login", { data: ADMIN });
  expect(r.ok()).toBeTruthy();
}

const ruleCount = async (page: Page, status: string) =>
  ((await (await page.request.get(`/api/rules?status=${status}`)).json()) as unknown[]).length;

test("the engine's signed rules and the switch show up in Rules and Topology", async ({ page }) => {
  expect((await page.request.post("/api/setup", { data: ADMIN })).status()).toBe(201);
  await signIn(page);
  await expect.poll(async () => (await (await page.request.get("/api/rules/summary")).json()).verified, { timeout: 45_000 }).toBe(3);
  await page.goto("/rules");
  await expect(page.getByRole("row").filter({ hasText: "tcp_dst=23" })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Verified \(3\)$/ })).toBeVisible();
  await page.getByRole("row").filter({ hasText: "tcp_dst=23" }).click();
  await expect(page.getByText("Signed by the controller")).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${IMG}/rules-live.png`, fullPage: true });
  await page.goto("/topology");
  await expect(page.getByText("Switch s1")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/Host on port/).first()).toBeVisible({ timeout: 15_000 });
  await page.screenshot({ path: `${IMG}/topology-live.png`, fullPage: true });
});

test("an unsigned rule appears live; an admin repairs it from the dashboard", async ({ page }) => {
  await signIn(page);
  await page.goto("/live");
  await expect(page.getByText("Alert only")).toBeVisible({ timeout: 15_000 });
  execFileSync("ovs-ofctl", ["-O", "OpenFlow13", "add-flow", "s1", "table=0,priority=300,arp,actions=drop"]);
  const item = page.getByRole("button", { name: /forged · priority 300/ }).first();
  await expect(item).toBeVisible({ timeout: 20_000 });
  await item.click();
  await expect(page.getByRole("heading", { name: "What happened" })).toBeVisible();
  await expect(page.getByText("FlowGuard did not change the switch.", { exact: false })).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${IMG}/live-detection.png`, fullPage: true });

  await page.goto("/rules");
  await page.getByRole("button", { name: /^Forged \(1\)$/ }).click();
  await page.getByRole("row").filter({ hasText: "eth_type=0x806" }).first().click();
  await expect(page.getByText("No signed rule exists for this slot")).toBeVisible();
  await page.getByRole("button", { name: "Repair this rule" }).click();
  await expect(page.getByRole("dialog", { name: "Repair this rule?" })).toBeVisible();
  await page.getByRole("button", { name: "Repair now" }).click();
  await expect(page.getByText("Repair requested")).toBeVisible();
  await expect.poll(() => ruleCount(page, "forged"), { timeout: 15_000 }).toBe(0);
  const flows = execFileSync("ovs-ofctl", ["-O", "OpenFlow13", "dump-flows", "s1", "table=0"]).toString();
  expect(flows).not.toContain("priority=300");

  await page.goto("/alerts");
  const repaired = page.getByRole("button", { name: /forged · priority 300/ }).filter({ hasText: "removed" }).first();
  await expect(repaired).toBeVisible({ timeout: 15_000 });
  await repaired.click();
  await expect(page.getByText("noticed through a repair requested from the dashboard")).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${IMG}/alerts-live.png`, fullPage: true });
  const audit = await (await page.request.get("/api/audit?action=rule_repair_requested")).json();
  expect(audit.total).toBe(1);
});
