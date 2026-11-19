// Screenshot capture for the presentation. Usage: node shots.mjs <phase> ; phase A = healthy, B = after a rule change.
import { chromium } from "@playwright/test";
import fs from "node:fs";

const OUT = "/mnt/d/sds/presentation/shots";
fs.mkdirSync(OUT, { recursive: true });
const phase = process.argv[2];
const WEB = "http://127.0.0.1:8787";
const CON = "http://127.0.0.1:8501";
const ADMIN = { username: "admin", password: "flowguard-demo" }; // demo account from RUN_AND_SHOW.md (local lab only)

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
const shot = async (name) => { await page.waitForTimeout(1500); await page.screenshot({ path: `${OUT}/${name}.png` }); console.log("shot", name); };

if (phase === "A") {
  // the console creates the demo admin the first time it opens
  await page.goto(CON, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(12000);
  await shot("console-overview");
}
const r = await page.request.post(`${WEB}/api/auth/login`, { data: ADMIN });
console.log("login", r.status());

async function go(path, name, extra) {
  await page.goto(WEB + path, { waitUntil: "networkidle" });
  if (extra) await extra();
  await shot(name);
}

if (phase === "A") {
  await go("/", "web-overview-dark");
  await go("/topology", "web-topology");
  await go("/rules", "web-rules");
  await go("/probes", "web-probes");
  await go("/ml", "web-ml");
  await go("/policy", "web-policy");
  await go("/reports", "web-reports");
  await go("/audit", "web-audit");
  await go("/settings", "web-settings");
  await go("/demo", "web-demo-start");
  // light theme copy of the overview
  await ctx.addInitScript(() => localStorage.setItem("fg-theme", "light"));
  await go("/", "web-overview-light");
}
if (phase === "B") {
  await go("/", "web-overview-alert");
  await go("/alerts", "web-alerts");
  await go("/live", "web-live");
  await go("/rules", "web-rules-forged");
  await go("/probes", "web-probes-after");
  await go("/ml", "web-ml-after");
  await page.goto(CON, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(10000);
  await shot("console-after");
}
if (phase === "C") {
  await page.goto(WEB + "/live", { waitUntil: "networkidle" });
  await page.getByText("shadow · priority 500").first().click();
  await shot("web-live-detail");
  await page.goto(WEB + "/alerts", { waitUntil: "networkidle" });
  await page.getByText("shadow · priority 500").first().click();
  await shot("web-alert-detail");
}
await browser.close();
