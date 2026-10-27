import { defineConfig, devices } from "@playwright/test";

/**
 * Onboarding and facility portal UX checks (onboarding-portal-ux epic). The onboarding steps use
 * synthetic identity, OTP and Terms answers; the portal checks sign in as the synthetic owner from
 * openmeter_mediator.tests.e2e_fixture with two crm.tests.e2e_express_fixture facilities, one
 * onboarded with a Partner Coupon and one without. Variables: BASE_URL, E2E_OWNER_PASSWORD,
 * E2E_PARTNER_MFL, E2E_NO_PARTNER_MFL, E2E_NO_PARTNER_FACILITY.
 * Run: npx playwright test --config e2e/onboarding-ux/playwright.config.ts
 */
export default defineConfig({
  testDir: ".",
  testMatch: /\.spec\.ts$/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 180_000,
  expect: { timeout: 20_000 },
  reporter: [
    ["list"],
    [
      "html",
      { open: "never", outputFolder: "../../playwright-report/onboarding-ux" },
    ],
  ],
  outputDir: "../../test-results/onboarding-ux",
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
      name: "desktop",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1000 },
      },
    },
  ],
});
