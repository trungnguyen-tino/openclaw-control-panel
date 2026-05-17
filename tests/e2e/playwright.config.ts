import { defineConfig, devices } from "@playwright/test";

// Boot order assumed:
//   1. `make build-ui` so static/dist exists
//   2. start gunicorn (or `make dev-api`) on :9998 against a throwaway state dir
//   3. `npx playwright test` against http://127.0.0.1:9998
//
// In CI we orchestrate via the release.yml workflow.

export default defineConfig({
  testDir: "./specs",
  timeout: 30_000,
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: process.env.OPENCLAW_PANEL_URL ?? "http://127.0.0.1:9998",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: devices["Desktop Chrome"] },
  ],
});
