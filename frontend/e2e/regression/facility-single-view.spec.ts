import { createServer, type Server } from 'http'
import { existsSync, readFileSync } from 'fs'
import { extname, join } from 'path'
import { fileURLToPath } from 'url'
import { expect, test, type Page, type Route } from '@playwright/test'

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

let server: Server
let origin = ''

test.beforeAll(async () => {
  server = createServer((req, res) => {
    const url = new URL(req.url || '/', 'http://local')
    let file = ''
    if (url.pathname === '/cx-portal') file = join(BUILD, 'cx-portal.html')
    else if (url.pathname.startsWith(ASSET_PREFIX)) file = join(BUILD, url.pathname.slice(ASSET_PREFIX.length))
    if (!file || !file.startsWith(BUILD) || !existsSync(file)) {
      res.writeHead(404).end()
      return
    }
    res.writeHead(200, { 'content-type': MIME[extname(file)] || 'application/octet-stream' })
    res.end(readFileSync(file))
  })
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
  origin = `http://127.0.0.1:${(server.address() as { port: number }).port}`
})

test.afterAll(() => server.close())

const facility = {
  facility_name: 'FID Regression Health Centre',
  mfl_code: '88776',
  facility_fid: 'FID-29-88776-5',
  keph_level: 'Level 3',
  hfr_sync_status: '',
  membership_status: 'Active',
}

// The real endpoint's envelope: frappe-ui `call` returns `message`, which is the
// status dict itself and carries its own human-readable `message` string.
const status = (data: Record<string, unknown>) => ({ json: { message: { message: 'Status synced.', ...data } } })

async function openFacility(
  page: Page,
  statusHandler: (route: Route) => Promise<void>,
  selectedFacility = facility,
  pollHandler?: (route: Route) => Promise<void>,
) {
  const statusCalls: Array<{ method: string; mfl_code?: string | null; http?: string }> = []
  await page.route('**/api/method/**', async (route) => {
    const method = route.request().url().split('/api/method/')[1].split('?')[0]
    const body = route.request().postDataJSON?.() || {}
    if (method === 'crm.api.website_redirect.get_portal_context')
      return route.fulfill({
        json: {
          message: {
            data: {
              user: 'operator@example.test',
              customer_accounts: [
                {
                  customer: 'Regression Customer',
                  organization: 'Regression Organization',
                  network: 'CareVerse Partner Network',
                  facilities: [selectedFacility],
                },
              ],
              ois: [],
              token_packages: [],
            },
          },
        },
      })
    if (method === 'crm.api.customer_experience.get_user_profile')
      return route.fulfill({ json: { message: { data: { email: 'operator@example.test' } } } })
    if (method === 'crm.api.hfr.ensure_provisioning_draft') {
      statusCalls.push({ method, mfl_code: body.mfl_code })
      return statusHandler(route)
    }
    if (method === 'crm.api.hfr.get_provisioning_status') {
      const mfl = new URL(route.request().url()).searchParams.get('mfl_code')
      statusCalls.push({ method, mfl_code: mfl, http: route.request().method() })
      return pollHandler ? pollHandler(route) : route.fulfill({ status: 500, json: {} })
    }
    return route.fulfill({ json: { message: { data: {} } } })
  })

  await page.goto(`${origin}/cx-portal`)
  await page.getByRole('button', { name: /Facilities/ }).first().click()
  await page.getByRole('button', { name: selectedFacility.facility_name }).click()
  return statusCalls
}

test('shows the saved HFR FID and offers a retry when status lookup temporarily fails', async ({ page }) => {
  let attempts = 0
  const statusCalls = await openFacility(page, async (route) => {
    attempts += 1
    if (attempts === 1)
      return route.fulfill({
        status: 503,
        json: { exc_type: 'Unavailable', message: 'Provisioning service temporarily unavailable.' },
      })
    return route.fulfill(status({ configured: true, status: 'deployed', progress: 100 }))
  })

  await expect(page.getByText('FID-29-88776-5', { exact: true })).toBeVisible()
  await expect(page.getByText('A verified HFR FID is required for deployment status and setup.')).toHaveCount(0)
  await expect(page.getByRole('alert')).toContainText('temporarily unavailable')
  await expect(page.getByRole('button', { name: 'Retry check' })).toBeVisible()
  expect(statusCalls[0]).toEqual({ method: 'crm.api.hfr.ensure_provisioning_draft', mfl_code: '88776' })

  await page.getByRole('button', { name: 'Retry check' }).click()
  await expect(page.getByText('Live', { exact: true })).toBeVisible()
  await expect(page.getByText('FID-29-88776-5', { exact: true })).toBeVisible()
  expect(statusCalls).toHaveLength(2)
  expect(statusCalls[1].mfl_code).toBe('88776')
})

test('a status service mismatch names the FID the portal actually sent for resolution', async ({ page }) => {
  const statusCalls = await openFacility(page, async (route) =>
    route.fulfill(
      status({
        configured: false,
        status: 'not_linked',
        message: 'An HFR Facility ID is required to look up HMIS implementation status.',
        journey: { phase: 'not_linked', steps: [], poll: false },
      }),
    ),
  )

  await expect(page.getByText('FID-29-88776-5', { exact: true })).toBeVisible()
  await expect(page.getByText('FID lookup needs attention', { exact: true })).toBeVisible()
  await expect(page.getByText(/portal has HFR FID FID-29-88776-5/)).toBeVisible()
  await expect(page.getByText('A verified HFR FID is required for deployment status and setup.')).toHaveCount(0)
  expect(statusCalls[0].mfl_code).toBe('88776')
})

test('shows the resolved FID, HTTP status, and correlation ID in deployment diagnostics', async ({ page }) => {
  const unlinkedFacility = { ...facility, facility_fid: '' }
  await openFacility(page, async (route) =>
    route.fulfill(
      status({
        configured: true,
        fid: 'FID-29-88776-5',
        status: 'unavailable',
        error_title: 'The deployment service could not return status',
        message: 'The status request failed.',
        correlation_id: 'crm-ta-req-123',
        error_details: '{\n  "http_status": 500,\n  "response": {\n    "response_text": "Internal Server Error"\n  }\n}',
      }),
    ),
    unlinkedFacility,
  )

  await page.getByRole('button', { name: 'View deployment diagnostics' }).click()
  const dialog = page.getByRole('dialog', { name: 'Deployment service diagnostics' })
  await expect(dialog).toBeVisible()
  await expect(dialog).toContainText('HTTP 500')
  await expect(dialog).toContainText('Internal Server Error')
  await expect(dialog).toContainText('Correlation ID: crm-ta-req-123')
  await expect(dialog).toContainText('FID-29-88776-5')
  await dialog.getByRole('button', { name: 'Close' }).click()
  await expect(dialog).toHaveCount(0)
})

test('a real status response is read as status, not as its message text', async ({ page }) => {
  // Regression: unwrap() returned the dict's `message` string, so every facility
  // showed "Not started / Implementation status has not been checked."
  await openFacility(page, async (route) => route.fulfill(status({ configured: true, status: 'Draft', progress: 0 })))

  await expect(page.getByText('Draft ready for review', { exact: true })).toBeVisible()
  await expect(page.getByText('Implementation status has not been checked.')).toHaveCount(0)
  await expect(page.getByText('Not started', { exact: true })).toHaveCount(0)
})

// Synthetic values on the reserved .test domain; never real sites or contacts.
const SITE_URL = 'https://site.example.test'
const ADMIN = 'admin@example.test'

const steps = (current: number, failed = -1) =>
  ['request', 'deploy', 'configure', 'live'].map((key, index) => ({
    key,
    label: ['Setup request received', 'Deploying HMIS site', 'Configuring facility and administrator', 'Ready to sign in'][index],
    state: failed >= 0 ? (index < failed ? 'done' : index === failed ? 'error' : 'upcoming') : index < current ? 'done' : index === current ? 'current' : 'upcoming',
  }))

test('a provisioned site shows its URL and how to sign in', async ({ page }) => {
  await openFacility(page, async (route) =>
    route.fulfill(
      status({
        configured: true,
        status: 'Deployed',
        progress: 100,
        journey: {
          phase: 'live',
          headline: 'Your HMIS site is ready',
          detail: 'Sign in with the facility administrator account below.',
          steps: steps(4),
          progress: 100,
          estimate: null,
          poll: false,
          checked_at: '2026-10-25T10:00:00',
          site: {
            url: SITE_URL,
            login_url: SITE_URL,
            admin_email: ADMIN,
            instructions: [
              `Open ${SITE_URL}`,
              `Sign in with ${ADMIN}`,
              'First time signing in? Use the HMIS welcome email or “Forgot password” on the sign-in page to set your password.',
            ],
          },
        },
      }),
    ),
  )

  const card = page.getByTestId('hmis-live-site')
  await expect(page.getByText('Live', { exact: true })).toBeVisible()
  await expect(card).toContainText(SITE_URL)
  await expect(card.getByText(`Sign in with ${ADMIN}`)).toBeVisible()
  const open = card.getByRole('link', { name: /Open HMIS/ })
  await expect(open).toHaveAttribute('href', SITE_URL)
  await expect(open).toHaveAttribute('target', '_blank')
  await expect(open).toHaveAttribute('rel', /noopener/)
  await expect(page.getByTestId('hmis-setup-journey')).toHaveCount(0)
  // A live site no longer asks for the go-live token allocation.
  await expect(page.getByText('Go-live token allocation')).toHaveCount(0)
})

test('setup in progress shows the stepper and wait estimate, and polls read-only status until live', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-10-25T10:00:00') })
  const deploying = {
    configured: true,
    status: 'Deploying',
    progress: 50,
    journey: {
      phase: 'deploying',
      headline: 'Deploying your HMIS site',
      detail: 'Your HMIS site is being deployed. You can keep using the portal; this page updates automatically.',
      steps: steps(1),
      progress: 50,
      estimate: { minutes: 10, source: 'progress', overdue: false, label: 'About 10 min remaining, based on progress so far' },
      site: null,
      poll: true,
      checked_at: '2026-10-25T10:00:00',
    },
  }
  const live = {
    configured: true,
    status: 'Deployed',
    journey: { ...deploying.journey, phase: 'live', steps: steps(4), progress: 100, estimate: null, poll: false, site: { url: SITE_URL, login_url: SITE_URL, admin_email: ADMIN, instructions: [`Open ${SITE_URL}`, `Sign in with ${ADMIN}`] } },
  }
  const statusCalls = await openFacility(
    page,
    async (route) => route.fulfill(status(deploying)),
    facility,
    async (route) => route.fulfill(status(live)),
  )

  const journey = page.getByTestId('hmis-setup-journey')
  await expect(page.getByText('Deploying', { exact: true })).toBeVisible()
  await expect(journey).toContainText('Deploying your HMIS site')
  await expect(page.getByTestId('hmis-setup-estimate')).toHaveText(/About 10 min remaining/)
  await expect(journey.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '50')
  await expect(journey.locator('li[data-state="done"]')).toHaveCount(1)
  await expect(journey.locator('li[data-state="current"]')).toContainText('Deploying HMIS site')
  await expect(page.getByTestId('hmis-auto-refresh')).toHaveText(/every 5 minutes/)
  expect(statusCalls.filter((call) => call.method.endsWith('get_provisioning_status'))).toHaveLength(0)

  // Polls every 5 minutes; nothing is read before then.
  await page.clock.fastForward('04:50')
  expect(statusCalls.filter((call) => call.method.endsWith('get_provisioning_status'))).toHaveLength(0)
  await page.clock.fastForward('00:15')
  await expect(page.getByTestId('hmis-live-site')).toContainText(SITE_URL)
  const polls = statusCalls.filter((call) => call.method.endsWith('get_provisioning_status'))
  expect(polls).toEqual([{ method: 'crm.api.hfr.get_provisioning_status', mfl_code: '88776', http: 'GET' }])
  // Polling is a read; it never re-sends the ensure (write) command.
  expect(statusCalls.filter((call) => call.method.endsWith('ensure_provisioning_draft'))).toHaveLength(1)
  await expect(page.getByTestId('hmis-auto-refresh')).toHaveCount(0)

  await page.clock.fastForward('10:00')
  expect(statusCalls.filter((call) => call.method.endsWith('get_provisioning_status'))).toHaveLength(1)
})

test('blocked setup says what is missing and does not poll', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-10-25T10:00:00') })
  const message = 'Automatic setup could not start because approved CRM values are missing for: licence.'
  const statusCalls = await openFacility(page, async (route) =>
    route.fulfill(
      status({
        configured: true,
        status: 'not_submitted',
        submission: { state: 'blocked', retryable: false, missing_fields: ['licence'], message },
        journey: { phase: 'blocked', headline: 'Setup needs information', detail: message, steps: steps(0, 0), progress: 0, estimate: null, site: null, poll: false },
      }),
    ),
  )

  await expect(page.getByText('Setup needs information', { exact: true })).toBeVisible()
  await expect(page.getByText('Setup request not sent')).toBeVisible()
  await expect(page.getByTestId('hmis-setup-journey').locator('li[data-state="error"]')).toContainText('Setup request received')
  await expect(page.getByTestId('hmis-auto-refresh')).toHaveCount(0)
  await page.clock.fastForward('10:00')
  expect(statusCalls.filter((call) => call.method.endsWith('get_provisioning_status'))).toHaveLength(0)
})

// Setup service v2.1: a deployed site is live only once its owner login exists.
const ownerLive = (ownerLogin: { status: string; email_sent: boolean }, passwordStep: string) => ({
  configured: true,
  status: 'Deployed',
  progress: 100,
  reported: { site_url: SITE_URL, admin_username: ADMIN, owner_login: { email: ADMIN, ...ownerLogin } },
  journey: {
    phase: 'live',
    label: 'Live',
    headline: 'Your HMIS site is ready',
    detail: 'Sign in with the facility administrator account below.',
    steps: steps(4),
    progress: 100,
    estimate: null,
    poll: false,
    checked_at: '2026-10-25T10:00:00',
    site: { url: SITE_URL, login_url: SITE_URL, admin_email: ADMIN, instructions: [`Open ${SITE_URL}`, `Sign in with ${ADMIN}`, passwordStep] },
  },
})

test('a deployed site whose owner login is still being created keeps configuring, then goes live', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-10-25T10:00:00') })
  const configuring = {
    configured: true,
    status: 'Deployed',
    progress: 100,
    reported: { site_url: SITE_URL, owner_login: { email: ADMIN, status: null, email_sent: false } },
    journey: {
      phase: 'configuring',
      label: 'Configuring',
      headline: 'Creating your administrator account',
      detail: 'Your HMIS site is deployed. The administrator sign-in is being created; this page updates automatically.',
      steps: steps(2),
      progress: 100,
      estimate: { minutes: 20, source: 'typical', overdue: false, label: 'Usually ready within about 20 min' },
      site: null,
      poll: true,
      checked_at: '2026-10-25T10:00:00',
    },
  }
  const live = ownerLive({ status: 'created', email_sent: true }, `Use the password in the HMIS credentials email sent to ${ADMIN}, or “Forgot password” on the sign-in page.`)
  await openFacility(page, async (route) => route.fulfill(status(configuring)), facility, async (route) => route.fulfill(status(live)))

  const journey = page.getByTestId('hmis-setup-journey')
  await expect(journey).toContainText('Creating your administrator account')
  await expect(journey.locator('li[data-state="current"]')).toContainText('Configuring facility and administrator')
  await expect(page.getByTestId('hmis-live-site')).toHaveCount(0)
  // Deployed alone is not go-live: the owner cannot sign in yet.
  await expect(page.getByText('Live', { exact: true })).toHaveCount(0)

  await page.clock.fastForward('05:05')
  const card = page.getByTestId('hmis-live-site')
  await expect(card).toContainText(SITE_URL)
  await expect(card).toContainText(`credentials email sent to ${ADMIN}`)
})

test('an undelivered credentials email points to Forgot password and shows no password', async ({ page }) => {
  const live = ownerLive({ status: 'created', email_sent: false }, 'The credentials email could not be delivered. Use “Forgot password” on the sign-in page to set your password.')
  await openFacility(page, async (route) => route.fulfill(status(live)))
  const card = page.getByTestId('hmis-live-site')
  await expect(card).toContainText('could not be delivered')
  await expect(card).toContainText('Forgot password')
  await expect(card.getByRole('button', { name: /password/i })).toHaveCount(0)
})

test('an owner login failure points at the configure step and stops polling', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-10-25T10:00:00') })
  const statusCalls = await openFacility(page, async (route) =>
    route.fulfill(
      status({
        configured: true,
        status: 'Deployed',
        progress: 100,
        journey: {
          phase: 'needs_attention',
          label: 'Needs attention',
          headline: 'Administrator account needs attention',
          detail: 'The HMIS site could not create the administrator sign-in yet. The setup service retries it on the next deployment; contact Network Support if this does not change.',
          steps: steps(0, 2),
          progress: 100,
          estimate: null,
          site: null,
          poll: false,
        },
      }),
    ),
  )
  const journey = page.getByTestId('hmis-setup-journey')
  await expect(page.getByText('Needs attention', { exact: true })).toBeVisible()
  await expect(journey.locator('li[data-state="error"]')).toContainText('Configuring facility and administrator')
  await expect(journey.locator('li[data-state="done"]')).toHaveCount(2)
  await page.clock.fastForward('10:00')
  expect(statusCalls.filter((call) => call.method.endsWith('get_provisioning_status'))).toHaveLength(0)
})
