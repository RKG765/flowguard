import { defineConfig, devices } from "@playwright/test";

// Live dashboard tests: a throw-away lab + engine (alert-only mode) + core started by tests/e2e_live/stack.py, and the
// Vite dev server proxying to that core. Needs root (Mininet/OVS); run with `sudo make test-e2e-live`.
const CORE_PORT = 18788;
const WEB_PORT = 5175;

export default defineConfig({
  testDir: "./e2e-live",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 90_000,
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${WEB_PORT}`, viewport: { width: 1440, height: 900 }, colorScheme: "dark", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 }, colorScheme: "dark" } }],
  webServer: [
    {
      command: `bash -c 'cd .. && .venv-core/bin/python tests/e2e_live/stack.py --core-port ${CORE_PORT} --response-mode alert_only'`,
      url: `http://127.0.0.1:${CORE_PORT}/api/health`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `npx vite --port ${WEB_PORT} --strictPort`,
      url: `http://127.0.0.1:${WEB_PORT}`,
      env: { FG_API_TARGET: `http://127.0.0.1:${CORE_PORT}` },
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
