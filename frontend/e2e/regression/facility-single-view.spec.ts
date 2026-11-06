import { randomUUID } from 'crypto'
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
  accountExtra: Record<string, unknown> = {},
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
                  ...accountExtra,
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

  await expect(page.getByTestId('facility-header-ids').getByText('FID-29-88776-5', { exact: true })).toBeVisible()
  await expect(page.getByText('A verified HFR FID is required for deployment status and setup.')).toHaveCount(0)
  await expect(page.getByRole('alert')).toContainText('temporarily unavailable')
  await expect(page.getByRole('button', { name: 'Retry check' })).toBeVisible()
  expect(statusCalls[0]).toEqual({ method: 'crm.api.hfr.ensure_provisioning_draft', mfl_code: '88776' })

  await page.getByRole('button', { name: 'Retry check' }).click()
  await expect(page.getByText('Live', { exact: true })).toBeVisible()
  await expect(page.getByTestId('facility-header-ids').getByText('FID-29-88776-5', { exact: true })).toBeVisible()
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

  await expect(page.getByTestId('facility-header-ids').getByText('FID-29-88776-5', { exact: true })).toBeVisible()
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

// Setup service API v2.0: named deployment steps, faster polling during deployment, "Live since".
test('a running deployment names its step, checks every 60 seconds, then shows when it went live', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-11-01T10:00:00') })
  const deploying = {
    configured: true,
    status: 'In Progress',
    progress: 45,
    journey: {
      phase: 'deploying',
      label: 'Deploying',
      headline: 'Deploying your HMIS site',
      detail: 'Your HMIS site is being deployed. You can keep using the portal; this page updates automatically.',
      steps: steps(1),
      progress: 45,
      estimate: null,
      site: null,
      deploy_step: { index: 6, total: 12, name: 'Service Units', label: 'Creating service units', state: 'running', text: 'Step 6 of 12 · Creating service units' },
      poll: true,
      poll_after_seconds: 60,
      checked_at: '2026-11-01T10:00:00',
    },
  }
  const live = {
    ...ownerLive({ status: 'created', email_sent: true }, `Use the password in the HMIS credentials email sent to ${ADMIN}, or “Forgot password” on the sign-in page.`),
  }
  live.journey = { ...live.journey, site: { ...live.journey.site, live_since: 'Live since 1 Nov 2026' } } as typeof live.journey
  const statusCalls = await openFacility(page, async (route) => route.fulfill(status(deploying)), facility, async (route) => route.fulfill(status(live)))

  await expect(page.getByTestId('hmis-deploy-step')).toHaveText(/Step 6 of 12 · Creating service units/)
  await expect(page.getByTestId('hmis-auto-refresh')).toHaveText(/every 60 seconds/)
  await page.clock.fastForward('00:50')
  expect(statusCalls.filter((call) => call.method.endsWith('get_provisioning_status'))).toHaveLength(0)
  await page.clock.fastForward('00:15')
  const card = page.getByTestId('hmis-live-site')
  await expect(card).toContainText(SITE_URL)
  await expect(page.getByTestId('hmis-live-since')).toHaveText('Live since 1 Nov 2026')
  await expect(page.getByTestId('hmis-deploy-step')).toHaveCount(0)
})

test('a failed deployment says which step it stopped at', async ({ page }) => {
  await openFacility(page, async (route) =>
    route.fulfill(
      status({
        configured: true,
        status: 'Failed',
        progress: 55,
        journey: {
          phase: 'needs_attention',
          label: 'Needs attention',
          headline: 'Setup needs attention',
          detail: 'The implementation team needs to review the latest deployment attempt. Contact Network Support if this does not change.',
          steps: steps(0, 1),
          progress: 55,
          estimate: null,
          site: null,
          deploy_step: { index: 7, total: 12, name: 'Laboratories', label: 'Setting up laboratories', state: 'failed', text: 'Stopped at step 7 of 12 · Setting up laboratories' },
          poll: false,
          poll_after_seconds: null,
          checked_at: '2026-11-01T10:00:00',
        },
      }),
    ),
  )
  const journey = page.getByTestId('hmis-setup-journey')
  await expect(journey).toContainText('Where setup stopped')
  await expect(page.getByTestId('hmis-deploy-step')).toHaveText(/Stopped at step 7 of 12 · Setting up laboratories/)
  await expect(journey.locator('li[data-state="error"]')).toContainText('Deploying HMIS site')
  await expect(page.getByTestId('hmis-auto-refresh')).toHaveCount(0)
})

// Temporary password: shown once to the HMIS owner, never in the polled status.
// Generated per run: a fixture value only, never a credential kept in source.
const TEMP_PASSWORD = `tmp-${randomUUID()}`
const credentialLive = (credentials: Record<string, unknown>) => {
  const live = ownerLive(
    { status: 'created', email_sent: false },
    'The credentials email could not be delivered. The facility administrator can view the temporary password once below. Change it after you first sign in.',
  )
  live.journey = { ...live.journey, site: { ...live.journey.site, credentials: { status: 'created', email_sent: false, password_available: true, owner_email_masked: 'a***@e***.test', viewed_on: null, viewed_by_you: false, can_view: false, ...credentials } } } as typeof live.journey
  return live
}

test('the owner views the temporary password once, must confirm saving it, and the card then says it was viewed', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  const reveals: string[] = []
  await openFacility(
    page,
    async (route) => route.fulfill(status(credentialLive({ can_view: true }))),
    facility,
    async (route) => route.fulfill(status(credentialLive({ viewed_on: '2026-11-01 10:05:00', viewed_by_you: true }))),
  )
  await page.route('**/api/method/crm.api.hfr.reveal_hmis_owner_password', async (route) => {
    reveals.push(route.request().method())
    return route.fulfill({ json: { message: { email: ADMIN, password: TEMP_PASSWORD, viewed_on: '2026-11-01 10:05:00' } } })
  })

  const panel = page.getByTestId('hmis-owner-password')
  await expect(page.getByText(TEMP_PASSWORD)).toHaveCount(0)
  await panel.getByRole('button', { name: 'View temporary password' }).click()
  const confirm = page.getByTestId('hmis-reveal-confirm')
  await expect(confirm).toContainText('shown one time only')
  await confirm.getByRole('button', { name: 'Not now' }).click()
  expect(reveals).toHaveLength(0)

  await panel.getByRole('button', { name: 'View temporary password' }).click()
  await page.getByTestId('hmis-reveal-confirm').getByRole('button', { name: 'Show password' }).click()
  const dialog = page.getByTestId('hmis-owner-password-dialog')
  await expect(dialog.getByTestId('hmis-owner-password-value')).toHaveText(TEMP_PASSWORD)
  await expect(dialog).toContainText(ADMIN)
  expect(reveals).toEqual(['POST'])

  await dialog.getByRole('button', { name: 'Copy' }).click()
  await expect(dialog.getByRole('button', { name: 'Copied' })).toBeVisible()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(TEMP_PASSWORD)

  // Escape and the backdrop do not close it; only the confirmed Close button does.
  await page.keyboard.press('Escape')
  await expect(dialog).toBeVisible()
  const close = dialog.getByRole('button', { name: 'Close' })
  await expect(close).toBeDisabled()
  await dialog.getByTestId('hmis-owner-password-saved').check()
  await close.click()
  await expect(dialog).toHaveCount(0)
  await expect(page.getByText(TEMP_PASSWORD)).toHaveCount(0)
  await expect(panel).toContainText('You viewed the temporary password on')
  await expect(panel).toContainText('cannot be shown again')
  await expect(panel.getByRole('button', { name: 'View temporary password' })).toHaveCount(0)
})

test('other portal users see who can view the temporary password, not a button', async ({ page }) => {
  await openFacility(page, async (route) => route.fulfill(status(credentialLive({ can_view: false }))))
  const panel = page.getByTestId('hmis-owner-password')
  await expect(panel).toContainText('Only the facility administrator (a***@e***.test) can view the temporary password, once')
  await expect(panel.getByRole('button')).toHaveCount(0)
})

test('a refused view explains why and shows no password', async ({ page }) => {
  await openFacility(page, async (route) => route.fulfill(status(credentialLive({ can_view: true }))))
  await page.route('**/api/method/crm.api.hfr.reveal_hmis_owner_password', (route) =>
    route.fulfill({
      status: 417,
      json: {
        exc_type: 'ValidationError',
        _server_messages: JSON.stringify([JSON.stringify({ message: 'The temporary password was already viewed on 1 Nov 2026. Contact Network Support if it was lost.' })]),
      },
    }),
  )
  await page.getByTestId('hmis-owner-password').getByRole('button', { name: 'View temporary password' }).click()
  await page.getByTestId('hmis-reveal-confirm').getByRole('button', { name: 'Show password' }).click()
  await expect(page.getByTestId('hmis-owner-password')).toContainText('already viewed')
  await expect(page.getByTestId('hmis-owner-password-dialog')).toHaveCount(0)
})

// ---------------------------------------------------------------------------
// Plan-aware facility page (cx-facility-page-ui): the commercial projection
// drives the summary, the plan panel, and the Quote -> Order -> Invoice ->
// Payment journey in every journey.
// ---------------------------------------------------------------------------

const timeBoundFacility = {
  ...facility,
  mfl_code: '7687',
  facility_name: 'Opt-in Network Clinic',
  hfr_facility_id: 'FID-29-7687-1',
  commercial: {
    journey: 'network_optin',
    journey_label: 'Network Opt-In',
    plan_type: 'time_bound',
    has_tokens: false,
    unavailable: false,
    plan: {
      name: 'Network subscription',
      source: 'optin_contract',
      status: 'Active',
      cycle: 'Quarterly',
      cycle_label: 'Billed quarterly',
      term_years: 5,
      term_label: '5 years',
      currency: 'KES',
      facilities_on_plan: 1,
      current_period: { start: '2026-11-01', end: '2027-01-30' },
      next_invoice: {
        label: 'Year 1 · Quarter 1',
        date: '2027-01-30',
        amount_incl_vat: 6960,
        projected: true,
      },
      schedule: [
        { label: 'Year 1 · Quarter 2', invoice_date: '2027-04-30', amount_incl_vat: 6960, projected: true, state: 'scheduled' },
      ],
    },
    quotes: [
      { name: 'SAL-QTN-2026-00001', label: 'Year 1', status_label: 'Accepted', amount: 27840, currency: 'KES' },
    ],
  },
  orders: [
    {
      name: 'SAL-ORD-2026-00035',
      display_title: 'Year 1 · Quarter 1 subscription',
      display_status: 'Confirmed',
      doc_kind: 'fixed_period',
      schedule_governed: true,
      is_draft: false,
      can_create_invoice: false,
      facility_mfls: ['7687'],
      transaction_date: '2026-11-01',
      grand_total: 6960,
      currency: 'KES',
      quotation: 'SAL-QTN-2026-00001',
    },
  ],
  invoices: [
    {
      name: 'ACC-SINV-2026-00017',
      invoice_number: 'ACC-SINV-2026-00017',
      amount: 0,
      due_date: '2026-11-15',
      facility_mfls: ['7687'],
      sales_orders: ['SAL-ORD-2026-00035'],
    },
  ],
  payments: [
    {
      name: 'PE-1',
      mode_of_payment: 'M-Pesa',
      reference_no: 'PG20261105',
      posting_date: '2026-11-05',
      invoice: 'ACC-SINV-2026-00017',
      status: 'Recorded',
      amount: 6960,
    },
  ],
}

test('a time-bound opt-in facility shows its plan, the full journey, and no token copy', async ({ page }) => {
  // An account-level order (no facility_mfls) must surface via the notice, not vanish.
  await openFacility(
    page,
    async (route) => route.fulfill(status({ configured: true, status: 'deployed', progress: 100 })),
    timeBoundFacility,
    undefined,
    { open_orders: [{ name: 'SAL-ORD-ACCT-1', transaction_date: '2026-10-01', grand_total: 500, currency: 'KES' }] },
  )

  // Plan panel: committed plan, not tokens.
  const plan = page.getByTestId('plan-panel')
  await expect(plan.getByTestId('plan-name')).toHaveText('Network subscription')
  await expect(plan.getByTestId('plan-status')).toHaveText('Active')
  await expect(plan.getByTestId('plan-cycle')).toHaveText('Billed quarterly')
  await expect(plan.getByTestId('plan-term')).toHaveText('5 years')
  await expect(plan.getByTestId('plan-next-invoice')).toContainText('Year 1 · Quarter 1')
  // current_period is an {start,end} object on the server; it must render formatted,
  // never raw JSON (must-fix 6).
  const period = plan.getByTestId('plan-current-period')
  await expect(period).toBeVisible()
  await expect(period).not.toContainText('{')
  await expect(period).toContainText('2027')

  // Summary: plan + next invoice cards; no token cards.
  await expect(page.getByTestId('facility-plan-card')).toBeVisible()
  await expect(page.getByTestId('facility-next-invoice')).toBeVisible()
  await expect(page.getByTestId('facility-available-tokens')).toHaveCount(0)

  // Journey: all four stages, quote first, all complete.
  const stepper = page.getByTestId('journey-stepper')
  await expect(stepper.getByText('Quotes', { exact: true })).toBeVisible()
  await expect(stepper.getByText('Orders', { exact: true })).toBeVisible()
  await expect(stepper.getByText('Invoices', { exact: true })).toBeVisible()
  await expect(stepper.getByText('Payments', { exact: true })).toBeVisible()
  await expect(stepper.locator('[data-state="done"]')).toHaveCount(4)

  // Stage sections carry the documents; the quote links to its order.
  await expect(page.getByTestId('stage-quote')).toContainText('SAL-QTN-2026-00001')
  await expect(page.getByTestId('stage-order')).toContainText('Year 1 · Quarter 1 subscription')
  await expect(page.getByTestId('stage-invoice')).toContainText('ACC-SINV-2026-00017')
  await expect(page.getByTestId('stage-payment')).toContainText('PG20261105')

  // Cross-stage links target real per-row ids (jumpTo uses getElementById).
  await expect(page.locator('#doc-SAL-QTN-2026-00001')).toHaveCount(1)
  await expect(page.locator('#doc-SAL-ORD-2026-00035')).toHaveCount(1)
  await expect(page.locator('#doc-ACC-SINV-2026-00017')).toHaveCount(1)
  await page.getByTestId('stage-invoice').getByRole('button', { name: 'For order SAL-ORD-2026-00035' }).click()
  await expect(page.locator('#doc-SAL-ORD-2026-00035')).toBeFocused()

  // The account-level order is surfaced, not dropped (I1).
  await expect(page.getByText('1 account-level records are not tied to one facility.')).toBeVisible()

  // No token copy anywhere on a time-bound facility.
  await expect(page.getByText(/tokens/i)).toHaveCount(0)
})

// A time-bound facility that also has a token meter: plan_type wins, so no token
// summary cards and no token go-live block (must-fix 2, SPEC 6 "time-bound with tokens").
const timeBoundWithTokensFacility = {
  ...timeBoundFacility,
  mfl_code: '7688',
  facility_name: 'Opt-in Hybrid Clinic',
  commercial: {
    ...timeBoundFacility.commercial,
    has_tokens: true,
  },
  token_balance: { status: 'ok', balance: 300, as_of: '2026-11-06 08:00:00' },
  orders: [
    {
      name: 'SAL-ORD-2026-00041',
      display_title: 'Year 1 · Quarter 1 subscription',
      display_status: 'Confirmed',
      doc_kind: 'fixed_period',
      schedule_governed: true,
      is_draft: false,
      can_create_invoice: false,
      facility_mfls: ['7688'],
      transaction_date: '2026-11-01',
      grand_total: 6960,
      currency: 'KES',
      quotation: 'SAL-QTN-2026-00001',
    },
  ],
  invoices: [
    {
      name: 'ACC-SINV-2026-00018',
      invoice_number: 'ACC-SINV-2026-00018',
      amount: 0,
      due_date: '2026-11-15',
      facility_mfls: ['7688'],
      sales_orders: ['SAL-ORD-2026-00041'],
    },
  ],
  payments: [
    {
      name: 'PE-2',
      mode_of_payment: 'M-Pesa',
      reference_no: 'PG20261106',
      posting_date: '2026-11-05',
      invoice: 'ACC-SINV-2026-00018',
      status: 'Recorded',
      amount: 6960,
    },
  ],
}

test('a time-bound facility with a token meter still shows the plan, not token copy', async ({
  page,
}) => {
  await openFacility(
    page,
    async (route) => route.fulfill(status({ configured: true, status: 'deployed', progress: 100 })),
    timeBoundWithTokensFacility,
  )

  await expect(page.getByTestId('facility-plan-card')).toBeVisible()
  await expect(page.getByTestId('facility-next-invoice')).toBeVisible()
  // No token-centric summary, no token CTA, no token go-live block (the Care Tokens
  // supplement in the plan panel is the only token mention and is accurate here).
  await expect(page.getByTestId('facility-available-tokens')).toHaveCount(0)
  await expect(page.getByTestId('facility-current-package')).toHaveCount(0)
  await expect(page.getByTestId('token-alert-card')).toHaveCount(0)
  await expect(page.getByRole('button', { name: /Top up tokens/ })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /Choose a plan/ })).toHaveCount(0)
})

const tokenFacility = {
  ...facility,
  mfl_code: '90001',
  facility_name: 'Token Express Clinic',
  hfr_facility_id: '',
  token_package: 'Starter',
  token_quantity: 100,
  token_balance: { status: 'ok', balance: 42, as_of: '2026-11-06 08:00:00' },
  commercial: {
    journey: 'self_onboarding',
    journey_label: 'Self-Onboarding',
    plan_type: 'token',
    has_tokens: true,
    unavailable: false,
    plan: { name: 'Starter', source: 'token_package', cycle: '', cycle_label: '', next_invoice: null },
    quotes: [],
  },
  orders: [
    {
      name: 'SAL-ORD-2026-00099',
      doc_kind: 'token',
      crm_token_package_item: 'TOK-A',
      display_title: 'Starter',
      display_status: 'Invoiced',
      is_draft: false,
      can_create_invoice: false,
      facility_mfls: ['90001'],
      transaction_date: '2026-10-20',
      grand_total: 12000,
      currency: 'KES',
    },
  ],
  invoices: [
    {
      name: 'ACC-INV-2026-00099',
      invoice_number: 'ACC-INV-2026-00099',
      amount: 12000,
      due_date: '2026-12-31',
      facility_mfls: ['90001'],
      sales_orders: ['SAL-ORD-2026-00099'],
    },
  ],
  payments: [],
}

test('a token facility keeps token summary and a three-stage journey without a quote', async ({ page }) => {
  await openFacility(
    page,
    async (route) => route.fulfill(status({ configured: false, status: 'not_configured' })),
    tokenFacility,
  )

  await expect(page.getByTestId('facility-available-tokens')).toContainText('42')
  await expect(page.getByTestId('facility-current-package')).toContainText('Starter')
  await expect(page.getByTestId('facility-plan-card')).toHaveCount(0)

  const stepper = page.getByTestId('journey-stepper')
  await expect(stepper.getByText('Quotes', { exact: true })).toHaveCount(0)
  await expect(stepper.getByText('Orders', { exact: true })).toBeVisible()
  await expect(stepper.getByText('Invoices', { exact: true })).toBeVisible()
  await expect(stepper.locator('[data-state="current"]')).toHaveCount(1)

  await expect(page.getByRole('button', { name: 'Choose payment' })).toBeVisible()
  await expect(page.getByRole('button', { name: /Top up tokens/ })).toBeVisible()
})

const unplannedFacility = {
  ...facility,
  mfl_code: '55555',
  facility_name: 'Unplanned Clinic',
  hfr_facility_id: '',
  commercial: {
    journey: 'unknown',
    journey_label: '',
    plan_type: 'unknown',
    has_tokens: false,
    unavailable: false,
    plan: { name: '', source: 'none', cycle: '', cycle_label: '', next_invoice: null },
    quotes: [],
  },
  orders: [],
  invoices: [],
  payments: [],
}

test('a facility without a plan shows the plan-less summary and a choose-a-plan action', async ({ page }) => {
  await openFacility(
    page,
    async (route) => route.fulfill(status({ configured: false, status: 'not_configured' })),
    unplannedFacility,
  )

  await expect(page.getByTestId('facility-plan-card')).toContainText('Not set up yet')
  await expect(page.getByTestId('plan-panel')).toContainText('No plan yet')
  await expect(page.getByRole('button', { name: 'Choose a plan' }).first()).toBeVisible()
  await expect(page.getByRole('button', { name: /Top up tokens/ })).toHaveCount(0)
})
