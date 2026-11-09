import { defineConfig, devices } from "@playwright/test";

/**
 * CareverseHIMS Value Express landing page and onboarding (value-express-redesign epic).
 * Onboarding uses synthetic identity, OTP, Terms and submit answers; the package catalogue
 * (Flex, Fixed and Custom) comes from the site, so seed it first on a dev site:
 *   bench --site <site> execute crm.demo.seed_token_package_catalog.run_value_express
 * Variables: BASE_URL. Run: npx playwright test --config e2e/value-express/playwright.config.ts
 */
export default defineConfig({
  testDir: ".",
  testMatch: /\.spec\.ts$/,
  workers: 1,
  retries: 0,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  outputDir: "../../test-results/value-express",
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
