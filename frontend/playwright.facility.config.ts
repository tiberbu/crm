import { defineConfig, devices } from '@playwright/test'

// Runs the actual built CX Portal bundle with only Frappe's JSON API mocked.
// No site, login session, or external service credentials are required.
export default defineConfig({
  testDir: './e2e/regression',
  testMatch: /(facility-single-view|facility-onboarding-network)\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  timeout: 60000,
  reporter: 'list',
  expect: { timeout: 10000 },
  projects: [{ name: 'facility-single-view', use: { ...devices['Desktop Chrome'] } }],
})
