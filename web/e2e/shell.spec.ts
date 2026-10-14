import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/** Serial end-to-end flow against a fresh core: first-run setup, shell, palette, theme, accessibility, sign-in. */
test.describe.configure({ mode: "serial" });

const ADMIN = { username: "admin", password: "e2e-admin-pass-1" };
const IMG = "../docs/img";

async function axe(page: Page) {
  // @axe-core/playwright is typed against a newer playwright-core Page; the runtime API is the same
  const r = await new AxeBuilder({ page: page as never }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const serious = r.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(serious.flatMap((v) => v.nodes.slice(0, 15).map((n) => `${v.id} | ${n.target.join(" ")} | ${(n.any[0]?.message ?? "").slice(0, 160)}`))).toEqual([]);
}

/** Each test gets a fresh browser context (no cookies): sign in through the API, the UI then restores the session. */
async function signIn(page: Page) {
  const r = await page.request.post("/api/auth/login", { data: ADMIN });
  expect(r.ok()).toBeTruthy();
}

test("first run redirects to setup and validates the form", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/setup$/);
  await expect(page.getByRole("heading", { name: "Create the first admin account" })).toBeVisible();
  await page.getByLabel("Password", { exact: true }).fill("short");
  await expect(page.getByText("At least 8 characters")).toBeVisible();
  await expect(page.getByRole("button", { name: "Create admin and continue" })).toBeDisabled();
  await axe(page);
  await page.screenshot({ path: `${IMG}/setup-dark.png` });
});

test("creating the admin lands on the Overview with honest empty states", async ({ page }) => {
  await page.goto("/setup");
  await page.getByLabel("Username").fill(ADMIN.username);
  await page.getByLabel("Password", { exact: true }).fill(ADMIN.password);
  await page.getByLabel("Confirm password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Create admin and continue" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { level: 1, name: "Overview" })).toBeVisible();
  await expect(page.getByText("No alerts yet")).toBeVisible();              // no detect-time number is invented
  await expect(page.getByText("No incidents")).toBeVisible();
  await expect(page.getByText("L2 Data-plane probes")).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: /engine/i }).first()).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${IMG}/overview-dark.png`, fullPage: true });
});

test("the live connection opens even without an engine", async ({ page }) => {
  await signIn(page);
  await page.goto("/");
  await expect(page.getByText(/Waiting for engine status|Engine not reporting/)).toBeVisible({ timeout: 10_000 });
});

test("Ctrl+K palette navigates, and planned pages say so", async ({ page }) => {
  await signIn(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Overview" })).toBeVisible(); // shell mounted: shortcut registered
  await page.keyboard.press("Control+k");
  const dialog = page.getByRole("dialog", { name: "Command palette" });
  await expect(dialog).toBeVisible();
  await page.keyboard.type("design system");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/design$/);
  await expect(page.getByRole("heading", { name: /Color tokens and measured contrast/ })).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${IMG}/design-dark.png`, fullPage: true });
  await page.goto("/probes");
  await expect(page.getByText("Probes is planned")).toBeVisible();
});

test("theme toggle switches to light and persists", async ({ page }) => {
  await signIn(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await axe(page);
  await page.screenshot({ path: `${IMG}/overview-light.png`, fullPage: true });
  await page.goto("/design");
  await axe(page);
  await page.screenshot({ path: `${IMG}/design-light.png`, fullPage: true });
  await page.getByRole("button", { name: "Theme: light" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});

test("reduced transparency makes glass solid; reduced motion stops the background animation", async ({ page }) => {
  await signIn(page);
  await page.goto("/design");
  const glassFilter = () => page.locator(".glass").first().evaluate((el) => getComputedStyle(el).backdropFilter);
  expect(await glassFilter()).toContain("blur");
  await page.getByRole("button", { name: /Reduced transparency: off/ }).click();
  expect(await glassFilter()).toBe("none");
  await page.getByRole("button", { name: /Reduced transparency: on/ }).click();
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.reload();
  const anim = await page.evaluate(() => getComputedStyle(document.body, "::before").animationName);
  expect(anim).toBe("none");
});

test("keyboard users get a skip link and a visible focus ring", async ({ page }) => {
  await signIn(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Overview" })).toBeVisible();
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to content" });
  await expect(skip).toBeFocused();
  const outline = await skip.evaluate((el) => getComputedStyle(el).outlineStyle);
  expect(outline).not.toBe("none");
});

test("sign out, wrong password, lockout, then sign in again", async ({ page }) => {
  await signIn(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("Username").fill(ADMIN.username);
  await page.getByLabel("Password", { exact: true }).fill("wrong-password-1");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Invalid username or password.")).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${IMG}/login-error-dark.png` });
  // lockout is per (ip, username): use another name so the admin is not locked out
  await page.getByLabel("Username").fill("someone-else");
  for (let i = 0; i < 5; i++) {
    await page.getByLabel("Password", { exact: true }).fill(`nope-nope-${i}`);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByText(/Invalid username or password|Too many failed attempts/)).toBeVisible();
  }
  await page.getByLabel("Password", { exact: true }).fill("nope-nope-x");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText(/Too many failed attempts\. Try again in \d+ s\./)).toBeVisible();
  await page.getByLabel("Username").fill(ADMIN.username);
  await page.getByLabel("Password", { exact: true }).fill(ADMIN.password);
  await page.reload(); // clears the countdown banner
  await page.getByLabel("Username").fill(ADMIN.username);
  await page.getByLabel("Password", { exact: true }).fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/$/);
});
