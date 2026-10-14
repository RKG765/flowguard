import { defineConfig, devices } from "@playwright/test";

// The end-to-end run boots a throw-away core (its own data dir, port 18787) and the Vite dev server (port 5174) that
// proxies /api to it. No engine runs here: the shell must cope honestly with "no engine status yet".
const CORE_PORT = 18787;
const WEB_PORT = 5174;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    viewport: { width: 1440, height: 900 },
    colorScheme: "dark", // the first visit follows the OS preference; the product is dark-first
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 }, colorScheme: "dark" } }],
  webServer: [
    {
      command: `bash -c 'cd .. && rm -rf /tmp/fg-e2e && FLOWGUARD_DATA_DIR=/tmp/fg-e2e .venv-core/bin/uvicorn --factory core.main:create_app --host 127.0.0.1 --port ${CORE_PORT}'`,
      url: `http://127.0.0.1:${CORE_PORT}/api/health`,
      reuseExistingServer: false,
      timeout: 60_000,
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
