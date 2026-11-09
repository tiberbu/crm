import { defineConfig, devices } from "@playwright/test";

/**
 * Public home page checks, as a guest. Needs BASE_URL (the CRM site).
 * Run: npx playwright test --config e2e/landing/playwright.config.ts
 */
export default defineConfig({
  testDir: ".",
  testMatch: /\.spec\.ts$/,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  outputDir: "../../test-results/landing",
  use: {
    baseURL: process.env.BASE_URL,
    ignoreHTTPSErrors: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
});
