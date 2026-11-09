import { defineConfig, devices } from '@playwright/test'

// Live proof against a real CRM site (no mocks): the CX portal, CRM backend and
// HMIS setup service all run for real. Needs LIVE_BASE_URL and LIVE_SID (a portal
// user's session cookie); the spec skips itself otherwise.
export default defineConfig({
  testDir: '.',
  testMatch: /hmis_provisioning_live\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  timeout: 180000,
  reporter: [['list']],
  expect: { timeout: 60000 },
  projects: [{ name: 'live', use: { ...devices['Desktop Chrome'] } }],
})
