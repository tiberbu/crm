import { defineConfig, devices } from '@playwright/test'

// Standalone proof config. The spec serves the built bundles itself and mocks
// the Frappe API, so no site, login or Paystack account is needed.
export default defineConfig({
  testDir: '.',
  testMatch: /cx_onboarding\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  timeout: 90000,
  reporter: [['list']],
  expect: { timeout: 10000 },
  projects: [{ name: 'proof', use: { ...devices['Desktop Chrome'] } }],
})
