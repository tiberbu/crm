import { createServer, type Server } from 'http'
import { existsSync, readFileSync } from 'fs'
import { extname, join } from 'path'
import { fileURLToPath } from 'url'
import { expect, test, type Page, type Route } from '@playwright/test'

// Runs the built self-onboarding bundle with only Frappe's JSON API mocked.
// Covers one OTP per identity submission and submitting with or without a Network ID.

const BUILD = fileURLToPath(new URL('../../../crm/public/frontend', import.meta.url)).replace(/\/$/, '')
const ASSET_PREFIX = '/assets/crm/frontend/'
const MIME: Record<string, string> = {
  '.css': 'text/css',
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.json': 'application/json',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
}
const NETWORK_ID = '623161'

let server: Server
let origin = ''

test.beforeAll(async () => {
  server = createServer((req, res) => {
    const url = new URL(req.url || '/', 'http://local')
    let file = ''
    if (url.pathname === '/facility-onboarding') file = join(BUILD, 'facility-onboarding.html')
    else if (url.pathname.startsWith(ASSET_PREFIX)) file = join(BUILD, url.pathname.slice(ASSET_PREFIX.length))
    if (!file || !file.startsWith(BUILD) || !existsSync(file)) {
      res.writeHead(404).end()
      return
    }
    let body: Buffer | string = readFileSync(file)
    if (extname(file) === '.html') body = body.toString().replace(/\{\{[^}]*\}\}/g, '')
    res.writeHead(200, { 'content-type': MIME[extname(file)] || 'application/octet-stream' })
    res.end(body)
  })
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
  origin = `http://127.0.0.1:${(server.address() as { port: number }).port}`
})

test.afterAll(() => server.close())

const ok = (route: Route, message: unknown) => route.fulfill({ json: { message } })

type Call = { method: string; body: Record<string, unknown> }

async function mockOnboarding(
  page: Page,
  { startDelayMs = 0, reused = false, provisioning = undefined as Record<string, unknown> | undefined } = {},
) {
  const calls: Call[] = []
  await page.route('**/api/method/crm.api.facility_onboarding.*', async (route) => {
    const method = route.request().url().split('?')[0].split('.').pop()!
    const body = route.request().postDataJSON?.() || {}
    calls.push({ method, body })
    if (method === 'start_identity') {
      if (startDelayMs) await new Promise((resolve) => setTimeout(resolve, startDelayMs))
      return ok(route, {
        success: true,
        data: {
          session_token: 'regression-token',
          reused,
          delivery: { channel: 'email', masked_destination: 'o***@example.com', status: 'sent', resend_after: 60 },
        },
      })
    }
    if (method === 'verify_otp')
      return ok(route, {
        success: true,
        data: {
          identity: { full_name: 'Amina Otieno' },
          account_email: 'amina@example.com',
          facilities: [
            { facility_id: 'FID-1', mfl_code: 'FID-1', facility_name: 'Alpha Clinic', onboarding_eligible: true },
          ],
        },
      })
    if (method === 'get_catalog')
      // Same contract as the server: a blank ID with no default Network returns no Network.
      return ok(route, {
        success: true,
        data: {
          network:
            body.partner_id === NETWORK_ID
              ? { name: 'net-a', display_name: 'Example Health Network', contact_email: 'help@example.com' }
              : {},
          packages: [
            {
              item_code: 'TOK-CORE',
              display_name: 'Core care operations',
              token_quantity: 100,
              price: 30000,
              price_ex_vat: 30000,
              vat_amount: 4800,
              gross_total: 34800,
              currency: 'KES',
            },
          ],
        },
      })
    if (method === 'get_self_onboarding_terms')
      return ok(route, {
        success: true,
        data: { document: 'Self-Onboarding Terms', rendered_html: '<p>Terms.</p>', content_hash: 'terms-hash' },
      })
    if (method === 'check_onboarding_conflicts')
      return ok(route, { success: true, data: { outcome: 'new', allowed_facility_ids: ['FID-1'] } })
    if (method === 'submit_onboarding')
      return ok(route, {
        success: true,
        data: {
          outcome: 'new',
          portal_status: 'sent',
          submissions: [{ submission: 'DEAL-1', facility: 'Alpha Clinic', mfl_code: 'FID-1' }],
          provisioning,
        },
      })
    return route.fulfill({ status: 404 })
  })
  return calls
}

async function startIdentity(page: Page) {
  await page.goto(`${origin}/facility-onboarding`)
  await page.getByRole('button', { name: 'Start your onboarding' }).click()
  await page.getByPlaceholder('Enter your ID number').fill('12345678')
}

async function reachReview(page: Page, networkId = '') {
  await startIdentity(page)
  await page.getByRole('button', { name: 'Find my facilities' }).click()
  await page.getByLabel(/Verification code: 1 \/ 6/).focus()
  await page.keyboard.type('123456')
  await page.getByRole('button', { name: 'Verify and continue' }).click()
  await page.locator('label').filter({ hasText: 'Alpha Clinic' }).locator('input[type="checkbox"]').check()
  await page.getByRole('button', { name: 'Continue to packages' }).click()
  await expect(page.getByRole('heading', { name: 'Choose packages' })).toBeVisible()
  if (networkId) {
    await page.getByTestId('partner-coupon-toggle').click()
    await page.getByPlaceholder('123456').fill(networkId)
  }
  const choose = page
    .getByRole('article')
    .filter({ has: page.getByRole('heading', { name: 'Core care operations' }) })
    .getByRole('button', { name: /Choose package|Selected/ })
  if (await choose.isVisible()) await choose.click().catch(() => {})
  await page.getByRole('button', { name: 'Review your choices' }).click()
  await expect(page.getByText('Self-Onboarding Terms').first()).toBeVisible()
}

test('one identity submission requests one OTP, even when the button is clicked repeatedly', async ({ page }) => {
  const calls = await mockOnboarding(page, { startDelayMs: 800 })
  await startIdentity(page)
  const find = page.getByRole('button', { name: 'Find my facilities' })
  // Repeat the click and press Enter while the first request is still in flight.
  await find.click()
  await find.click({ force: true, timeout: 500 }).catch(() => {})
  await page.getByPlaceholder('Enter your ID number').press('Enter', { timeout: 500 }).catch(() => {})
  await expect(page.getByText(/A 6-digit code was sent by email to/)).toBeVisible()
  expect(calls.filter((call) => call.method === 'start_identity')).toHaveLength(1)
})

test('a restart within the resend window says the earlier code is still the one to use', async ({ page }) => {
  await mockOnboarding(page, { reused: true })
  await startIdentity(page)
  await page.getByRole('button', { name: 'Find my facilities' }).click()
  await expect(page.getByText(/We already sent a 6-digit code by email to o\*\*\*@example.com/)).toBeVisible()
  await expect(page.getByText(/no new code was sent/)).toBeVisible()
})

test('submits without a Network ID once the terms are accepted', async ({ page }) => {
  const calls = await mockOnboarding(page)
  await reachReview(page)

  await expect(page.getByTestId('network-blocker')).toHaveCount(0)
  await expect(page.getByTestId('review-partner-coupon')).toContainText('Not applied')
  await expect(page.getByTestId('no-partner-coupon-note')).toBeVisible()
  await page.getByTestId('terms-acceptance').check()
  const submit = page.getByRole('button', { name: 'Submit your request' })
  await expect(submit).toBeEnabled()
  await submit.click()
  await expect(page.getByText('Your request has been submitted')).toBeVisible()

  const submitted = calls.find((call) => call.method === 'submit_onboarding')
  expect(submitted?.body.partner_id || '').toBe('')
})

test('submits with a Network ID once the terms are accepted', async ({ page }) => {
  const calls = await mockOnboarding(page)
  await reachReview(page, NETWORK_ID)

  await expect(page.getByTestId('review-partner-coupon')).toContainText(NETWORK_ID)
  await expect(page.getByTestId('review-partner-coupon')).toContainText('Example Health Network')
  await page.getByTestId('terms-acceptance').check()
  await page.getByRole('button', { name: 'Submit your request' }).click()
  await expect(page.getByText('Your request has been submitted')).toBeVisible()

  const submitted = calls.find((call) => call.method === 'submit_onboarding')
  expect(submitted?.body.partner_id).toBe(NETWORK_ID)
})

test('the success screen says HMIS setup has already started for each facility', async ({ page }) => {
  await mockOnboarding(page, { provisioning: { state: 'started', facilities: ['FID-1'] } })
  await reachReview(page)
  await page.getByTestId('terms-acceptance').check()
  await page.getByRole('button', { name: 'Submit your request' }).click()

  await expect(page.getByText('Your request has been submitted')).toBeVisible()
  await expect(page.getByTestId('success-hmis-setup-started')).toHaveText(/HMIS setup started/)
  const note = page.getByTestId('success-hmis-setup-note')
  await expect(note).toContainText('We have started setting up your HMIS site')
  await expect(note).toContainText('keeps running while you set your password')
  // "Started", never "ready": the site is not live yet.
  await expect(note).not.toContainText(/ready/i)
})

test('the success screen does not claim setup started when it could not be queued', async ({ page }) => {
  await mockOnboarding(page, { provisioning: { state: 'deferred', facilities: [] } })
  await reachReview(page)
  await page.getByTestId('terms-acceptance').check()
  await page.getByRole('button', { name: 'Submit your request' }).click()

  await expect(page.getByText('Your request has been submitted')).toBeVisible()
  await expect(page.getByTestId('success-hmis-setup-started')).toHaveCount(0)
  await expect(page.getByTestId('success-hmis-setup-note')).toHaveCount(0)
})
