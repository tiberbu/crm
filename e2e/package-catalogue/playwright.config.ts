import { defineConfig, devices } from "@playwright/test";

/**
 * Settings › Packages (package-catalogue-admin epic): a Sales Manager runs the Value Express
 * catalogue and the landing page and onboarding follow it.
 * Needs two synthetic users on the site and their passwords in the environment:
 *   SM_EMAIL / SM_PASSWORD (Sales Manager), SU_EMAIL / SU_PASSWORD (Sales User), BASE_URL.
 * Packages it adds are named "E2E …"; remove them afterwards with
 *   bench --site <site> execute crm.demo.package_catalogue_e2e.remove_e2e_packages
 * Run: npx playwright test --config e2e/package-catalogue/playwright.config.ts
 */
export default defineConfig({
  testDir: ".",
  testMatch: /\.spec\.ts$/,
  workers: 1,
  retries: 0,
  timeout: 180_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  outputDir: "../../test-results/package-catalogue",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: process.env.BASE_URL,
    viewport: { width: 1440, height: 900 },
    ignoreHTTPSErrors: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
