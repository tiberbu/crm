import { randomUUID } from 'crypto'
import { mkdirSync } from 'fs'
import { join } from 'path'
import { expect, test, type Locator, type Page } from '@playwright/test'
import type { Server } from 'http'
import { auditLayout, startPortalServer } from './portalFixture'

// Express onboarding, on-behalf path (P-136): the ID step shows the on-behalf option as a
// card, and a verified ID with no facilities gets a decision panel whose primary action
// opens the administrator form. The onboarding API is mocked.
const SHOTS = process.env.SCREENSHOT_DIR || ''
const BRAND = 'rgb(188, 24, 35)'

let server: Server
let origin = ''
test.beforeAll(async () => ({ server, origin } = await startPortalServer()))
test.afterAll(() => server.close())

async function mockOnboarding(page: Page, facilities: unknown[] = []) {
  const identity = {
    full_name: 'Synthetic Person',
    email: 's***n@example.test',
    phone: '071******00',
  }
  await page.route('**/api/method/**', async (route) => {
    const method = route
      .request()
      .url()
      .split('/api/method/')[1]
      .split('?')[0]
      .split('.')
      .pop()
    const answers: Record<string, unknown> = {
      start_identity: {
        session_token: randomUUID(),
        identity,
        delivery: {
          channel: 'sms',
          masked_destination: identity.phone,
          status: 'sent',
          resend_after: 60,
        },
      },
      verify_otp: {
        state: 'ready',
        identity,
        account_email: 'synthetic.owner@example.test',
        facilities,
      },
    }
    return route.fulfill({
      json: { message: method && method in answers ? answers[method] : {} },
    })
  })
  await page.goto(`${origin}/facility-onboarding`)
}

async function verifyId(page: Page) {
  await page.getByPlaceholder('Enter your ID number').fill('12345678')
  await page.getByRole('button', { name: /Verify & Find My Facility/ }).click()
  await page.getByLabel(/1 \/ 6/).click()
  await page.keyboard.type('123456')
  await page
    .locator('form button:not([type]), form button[type=submit]')
    .first()
    .click()
    .catch(() => {})
}

async function weightAtMost600(locator: Locator) {
  const weights = await locator.evaluateAll((nodes) =>
    nodes.map((node) => ({
      weight: Number(getComputedStyle(node).fontWeight),
      text: (node.textContent || '').slice(0, 40),
      tag: node.tagName,
    })),
  )
  expect(weights.filter((w) => w.weight > 600)).toEqual([])
}

async function shot(page: Page, name: string, project: string) {
  if (!SHOTS) return
  mkdirSync(SHOTS, { recursive: true })
  await page.screenshot({
    path: join(SHOTS, `${project}-${name}.png`),
    fullPage: true,
  })
}

test('the ID step offers the on-behalf path as a visible option card', async ({
  page,
}, info) => {
  await mockOnboarding(page)
  const card = page.getByTestId('admin-path-card')
  await expect(
    card.getByRole('heading', { name: 'Not the registered owner?' }),
  ).toBeVisible()
  await expect(card).toContainText('one-time code')
  await weightAtMost600(card.locator('h2, p'))
  const issues = await auditLayout(page)
  expect(issues, JSON.stringify(issues, null, 1)).toEqual([])
  await shot(page, 'onboarding-id-on-behalf', info.project.name)

  await page.getByTestId('admin-path-toggle').click()
  await expect(
    page.getByRole('heading', { name: 'Setting up on behalf of a facility?' }),
  ).toBeVisible()
  await expect(page.getByTestId('admin-reference-input')).toBeFocused()
  await page.getByTestId('admin-path-back').click()
  await expect(card).toBeVisible()
})

test('no facilities for the ID leads to a clear on-behalf decision', async ({
  page,
}, info) => {
  await mockOnboarding(page, [])
  await verifyId(page)
  const panel = page.getByTestId('no-facilities-panel')
  await expect(
    page.getByRole('heading', {
      name: 'No facilities are registered to this ID',
      level: 1,
    }),
  ).toBeVisible()
  await expect(panel).toContainText('continue on their behalf')
  await expect(panel.locator('.nofac-steps li')).toHaveCount(3)
  const primary = panel.getByTestId('no-facilities-on-behalf')
  await expect(primary).toHaveCSS('background-color', BRAND)
  // Nothing to select, so the disabled Continue button is not competing for attention.
  await expect(
    page.getByRole('button', { name: /Continue to Packages/ }),
  ).toHaveCount(0)
  await weightAtMost600(panel.locator('p, li'))
  const issues = await auditLayout(page)
  expect(issues, JSON.stringify(issues, null, 1)).toEqual([])
  await shot(page, 'onboarding-no-facilities', info.project.name)

  await primary.click()
  await expect(
    page.getByRole('heading', { name: 'Setting up on behalf of a facility?' }),
  ).toBeVisible()
  await expect(page.getByTestId('admin-reference-input')).toBeFocused()
})

test('no facilities: the owner can go back and use a different ID', async ({
  page,
}) => {
  await mockOnboarding(page, [])
  await verifyId(page)
  await page.getByTestId('no-facilities-different-id').click()
  await expect(page.getByPlaceholder('Enter your ID number')).toBeVisible()
  await expect(page.getByTestId('admin-path-card')).toBeVisible()
})

test('a verified owner with facilities sees no on-behalf panel', async ({
  page,
}) => {
  await mockOnboarding(page, [
    {
      facility_id: 'FID-00-OB-01',
      facility_name: 'Synthetic Clinic',
      mfl_code: 'OB-01',
      facility_level: 'Level 3',
      onboarding_eligible: true,
    },
  ])
  await verifyId(page)
  await expect(
    page.getByRole('heading', {
      name: 'Select the facility you want to onboard',
    }),
  ).toBeVisible()
  await expect(page.getByTestId('no-facilities-panel')).toHaveCount(0)
  await expect(
    page.getByText('No facilities are registered to this ID'),
  ).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: /Continue to Packages/ }),
  ).toBeVisible()
})
