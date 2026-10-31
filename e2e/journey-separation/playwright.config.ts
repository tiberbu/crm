import { defineConfig, devices } from "@playwright/test";

/**
 * Network Opt-In and Partner Coupon on one network, live on a dev site (no mocks except the
 * external identity registry). Needs the bench on this machine for the synthetic fixture
 * (crm.tests.e2e_journey_separation_fixture), which the spec sets up and tears down itself.
 * Variables: BASE_URL (https), SITE, BENCH_DIR. Run:
 *   npx playwright test --config e2e/journey-separation/playwright.config.ts
 */
export default defineConfig({
  testDir: ".",
  testMatch: /\.spec\.ts$/,
  workers: 1,
  retries: 0,
  timeout: 180_000,
  expect: { timeout: 20_000 },
  reporter: [["list"]],
  outputDir: "../../test-results/journey-separation",
  use: {
    baseURL: process.env.BASE_URL,
    ignoreHTTPSErrors: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "desktop",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 900 },
      },
    },
  ],
});
