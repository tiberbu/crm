import { defineConfig, devices } from "@playwright/test";

/**
 * HMIS token top-up journey against a real CRM site with OpenMeter (openmeter_mediator ADR-004).
 * Needs the synthetic fixture from openmeter_mediator.tests.e2e_fixture and these variables:
 * BASE_URL, GATEWAY_URL, E2E_SITE_KEY, E2E_OWNER_PASSWORD, E2E_FINANCE_PASSWORD.
 * Run: npx playwright test --config e2e/metering/playwright.config.ts
 */
export default defineConfig({
  testDir: ".",
  testMatch: /\.spec\.ts$/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 300_000,
  expect: { timeout: 20_000 },
  reporter: [
    ["list"],
    [
      "html",
      { open: "never", outputFolder: "../../playwright-report/metering" },
    ],
  ],
  outputDir: "../../test-results/metering",
  use: {
    baseURL: process.env.BASE_URL,
    ignoreHTTPSErrors: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    actionTimeout: 20_000,
    navigationTimeout: 45_000,
  },
  projects: [
    {
      name: "metering",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1000 },
      },
    },
  ],
});
