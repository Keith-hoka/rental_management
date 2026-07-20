import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  // The dev backend runs a single worker whose event loop blocks on argon2
  // hashing, so many parallel Playwright workers saturate it on slow CI
  // runners. Run serially in CI for reliability; stay parallel locally.
  // The extra retry is a cheap safety net for unrelated CI hiccups.
  workers: process.env.CI ? 1 : undefined,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: "http://localhost:3000",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
