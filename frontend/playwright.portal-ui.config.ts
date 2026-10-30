import { defineConfig, devices } from '@playwright/test'

// CX Portal layout audit: the built bundle with Frappe's JSON API mocked, at phone,
// tablet, laptop and desktop widths. No site or login is required.
export default defineConfig({
  testDir: './e2e/regression',
  testMatch:
    /(portal-layout|token-alerts|onboarding-layout|portal-typography)\.spec\.ts/,
  fullyParallel: true,
  timeout: 60000,
  reporter: 'list',
  expect: { timeout: 10000 },
  projects: [
    {
      name: 'phone',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 390, height: 844 },
        hasTouch: true,
      },
    },
    {
      name: 'tablet',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 768, height: 1024 },
      },
    },
    {
      name: 'laptop',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1280, height: 800 },
      },
    },
    {
      name: 'desktop',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1536, height: 900 },
      },
    },
  ],
})
