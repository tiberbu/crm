import { createServer, type Server } from 'http'
import { existsSync, mkdirSync, readFileSync } from 'fs'
import { extname, join } from 'path'
import { fileURLToPath } from 'url'
import { expect, test, type Page, type Route } from '@playwright/test'

// Desktop/mobile proof for the Customer Experience onboarding wizard and portal.
// Real production bundles (crm/public/frontend, built by `vite build`) run in a
// real browser; only the Frappe API and Paystack are mocked, so nothing is charged.

const BUILD = fileURLToPath(
  new URL('../../../crm/public/frontend', import.meta.url),
).replace(/\/$/, '')
const OUT = process.env.PROOF_OUT || '/tmp/cx-proof'
const ASSET_PREFIX = '/assets/crm/frontend/'
const MIME: Record<string, string> = {
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.html': 'text/html',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
  '.json': 'application/json',
}

const PACKAGES = [
  {
    item_code: 'TOK-CORE',
    display_name: 'Core care operations',
    description: 'A starting package for everyday facility workflows.',
    coverage_summary: 'About 100 routine transactions per month.',
    token_quantity: 100,
    price: 30000,
    price_ex_vat: 30000,
    vat_amount: 4800,
    gross_total: 34800,
    vat_rate: 16,
    vat_label: 'VAT (16%)',
    currency: 'KES',
  },
  {
    item_code: 'TOK-STD',
    display_name: 'Standard care operations',
    description: 'Balanced capacity for regular clinical and billing activity.',
    coverage_summary: 'About 300 routine transactions per month.',
    token_quantity: 300,
    price: 75000,
    price_ex_vat: 75000,
    vat_amount: 12000,
    gross_total: 87000,
    vat_rate: 16,
    vat_label: 'VAT (16%)',
    currency: 'KES',
  },
]

const FACILITIES = [
  {
    facility_id: 'FID-1',
    mfl_code: '10001',
    facility_name: 'Alpha Community Clinic',
    classification: 'Level 3',
    facility_type: 'Dispensary',
  },
  {
    facility_id: 'FID-2',
    mfl_code: '10002',
    facility_name: 'Bravo Family Hospital With A Deliberately Long Name',
    classification: 'Level 4',
    facility_type: 'Hospital',
  },
]

const ok = (route: Route, message: unknown) =>
  route.fulfill({ json: { message } })

const fail = (route: Route, text: string, exc = 'ValidationError') =>
  route.fulfill({
    status: 417,
    json: {
      exc_type: exc,
      _server_messages: JSON.stringify([JSON.stringify({ message: text })]),
    },
  })

let server: Server
let origin = ''

test.beforeAll(async () => {
  mkdirSync(OUT, { recursive: true })
  server = createServer((req, res) => {
    const url = new URL(req.url || '/', 'http://local')
    const entries: Record<string, string> = {
      '/facility-onboarding': 'facility-onboarding.html',
      '/cx-portal': 'cx-portal.html',
    }
    let file = ''
    if (entries[url.pathname]) file = join(BUILD, entries[url.pathname])
    else if (url.pathname.startsWith(ASSET_PREFIX))
      file = join(BUILD, url.pathname.slice(ASSET_PREFIX.length))
    else if (url.pathname === '/__paystack__') {
      res.writeHead(200, { 'content-type': 'text/html' })
      res.end('<h1>Paystack sandbox checkout (mock)</h1>')
      return
    }
    if (!file || !file.startsWith(BUILD) || !existsSync(file)) {
      res.writeHead(404).end()
      return
    }
    let body: Buffer | string = readFileSync(file)
    if (extname(file) === '.html') {
      body = body
        .toString()
        .replace(/\{\{\s*\(csrf_token[^}]*\}\}/g, '""')
        .replace(/\{\{[^}]*\}\}/g, '')
    }
    res.writeHead(200, {
      'content-type': MIME[extname(file)] || 'application/octet-stream',
    })
    res.end(body)
  })
  await new Promise<void>((done) => server.listen(0, '127.0.0.1', done))
  origin = `http://127.0.0.1:${(server.address() as { port: number }).port}`
})

test.afterAll(() => server.close())

async function expectNoOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  )
  expect(overflow, 'horizontal overflow in px').toBeLessThanOrEqual(1)
}

async function shot(page: Page, name: string) {
  await expectNoOverflow(page)
  await page.screenshot({ path: join(OUT, `${name}.png`), fullPage: true })
}

function mockOnboarding(page: Page, resendAfter = 60) {
  const seen: string[] = []
  return page
    .route('**/api/method/crm.api.facility_onboarding.*', async (route) => {
      const method = route.request().url().split('?')[0].split('.').pop()!
      const body = route.request().postDataJSON?.() || {}
      seen.push(method)
      if (method === 'start_identity')
        return ok(route, {
          success: true,
          data: {
            session_token: 'proof-token',
            challenge_started: true,
            delivery: {
              channel: 'email',
              masked_destination: 'o***@example.com',
              status: 'sent',
              expires_in: 600,
              resend_after: resendAfter,
            },
          },
        })
      if (method === 'resend_otp')
        return ok(route, {
          success: true,
          data: {
            sent: true,
            delivery: {
              channel: 'sms',
              masked_destination: '254******78',
              status: 'sent',
              expires_in: 600,
              resend_after: resendAfter,
            },
          },
        })
      if (method === 'verify_otp')
        return body.otp === '123456'
          ? ok(route, {
              success: true,
              data: {
                identity: { full_name: 'Amina Otieno' },
                facilities: FACILITIES,
              },
            })
          : fail(
              route,
              'The verification code is incorrect or expired.',
              'PermissionError',
            )
      if (method === 'get_catalog')
        return ok(route, {
          success: true,
          data: {
            network: {
              name: 'net-a',
              display_name: 'Example Health Network',
              contact_email: 'help@example.com',
            },
            packages: PACKAGES,
          },
        })
      if (method === 'get_self_onboarding_terms')
        return ok(route, {
          success: true,
          data: {
            document: 'Self-Onboarding Terms',
            rendered_html: '<p>Terms for self-onboarded facilities.</p>',
            content_hash: 'terms-hash',
          },
        })
      if (method === 'check_onboarding_conflicts')
        return ok(route, {
          success: true,
          data: { outcome: 'new', allowed_facility_ids: ['FID-1', 'FID-2'] },
        })
      if (method === 'submit_onboarding')
        return ok(route, {
          success: true,
          data: {
            outcome: 'new',
            portal_status: 'sent',
            submissions: [
              {
                submission: 'OIS-2026-00031',
                status: 'Processed',
                facility: 'Alpha Community Clinic',
                quotation: 'QTN-2026-00031',
                sales_order: 'SAL-ORD-2026-00031',
              },
            ],
          },
        })
      return route.fulfill({ status: 404 })
    })
    .then(() => seen)
}

async function typeCode(page: Page, code: string) {
  await page.getByLabel(/Verification code: 1 \/ 6/).focus()
  await page.keyboard.type(code)
}

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
]

for (const vp of VIEWPORTS) {
  test.describe(`onboarding wizard (${vp.name})`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height } })

    test('identity to submission with privacy-safe delivery, keyboard OTP, VAT review and back/edit', async ({
      page,
    }) => {
      const calls = await mockOnboarding(page)
      await page.goto(`${origin}/facility-onboarding`)
      await shot(page, `${vp.name}-onboarding-1-welcome`)

      await page
        .getByRole('button', { name: /Start secure onboarding/ })
        .click()
      await page.getByPlaceholder('Enter your ID number').fill('12345678')
      await shot(page, `${vp.name}-onboarding-2-identity`)
      await page.getByRole('button', { name: 'Find my facilities' }).click()

      // Delivery status is privacy-safe and does not reveal whether an ID matched.
      await expect(
        page.getByText(/If your details match our records/),
      ).toBeVisible()
      await expect(page.getByText(/expires in 10 minutes/)).toBeVisible()
      await expect(
        page.getByRole('button', { name: /Resend code in/ }),
      ).toBeDisabled()
      await expect(page.locator('body')).not.toContainText('owner@example.com')

      // Wrong code: inline error, boxes cleared, wizard stays on the OTP step.
      await typeCode(page, '000000')
      await page.getByRole('button', { name: 'Verify and continue' }).click()
      await expect(page.getByRole('alert')).toContainText(
        'incorrect or expired',
      )
      await shot(page, `${vp.name}-onboarding-3-otp-error`)

      await typeCode(page, '123456')
      await shot(page, `${vp.name}-onboarding-4-otp-filled`)
      await page.getByRole('button', { name: 'Verify and continue' }).click()

      await expect(
        page.getByText('Bravo Family Hospital With A Deliberately Long Name'),
      ).toBeVisible()
      await page.getByText('Alpha Community Clinic').click()
      await page
        .getByText('Bravo Family Hospital With A Deliberately Long Name')
        .click()
      await shot(page, `${vp.name}-onboarding-5-facilities`)
      await page.getByRole('button', { name: 'Continue to pricing' }).click()

      await expect(page.getByText('Choose your token package')).toBeVisible()
      await expect(page.getByText(/Total\s+\S*\s*34,800/).first()).toBeVisible()
      await shot(page, `${vp.name}-onboarding-6-packages`)
      await page.getByRole('button', { name: 'Confirm your data' }).click()

      // Review shows server-supplied totals for two facilities and offers Edit/Back.
      await expect(page.getByText('Total incl. VAT')).toBeVisible()
      await expect(page.getByText(/69,600/).first()).toBeVisible()
      await expect(page.locator('body')).not.toContainText(
        /invoice|payment|pay now/i,
      )
      await expect(
        page.getByRole('button', { name: 'Submit facility onboarding' }),
      ).toBeDisabled()
      await page.getByPlaceholder('you@example.com').fill('sam@example.com')
      await page.getByPlaceholder('000000').fill('123456')
      await page.getByRole('checkbox').check()
      await expect(
        page.getByRole('button', { name: 'Submit facility onboarding' }),
      ).toBeEnabled()
      await shot(page, `${vp.name}-onboarding-7-review`)

      await page.getByRole('button', { name: 'Back to package' }).click()
      await expect(page.getByText('Choose your token package')).toBeVisible()
      await page.getByRole('button', { name: 'Confirm your data' }).click()
      await expect(page.getByText('Terms and Conditions').first()).toBeVisible()
      await page.getByPlaceholder('you@example.com').fill('sam@example.com')
      await page.getByRole('checkbox').check()
      await page
        .getByRole('button', { name: 'Submit facility onboarding' })
        .click()
      await expect(page.getByText('Your onboarding has started')).toBeVisible()
      await expect(page.getByText(/password setup instructions/i)).toBeVisible()
      await expect(page.locator('body')).not.toContainText(
        /invoice|payment|pay now/i,
      )
      await shot(page, `${vp.name}-onboarding-8-success`)
      expect(calls).toContain('submit_onboarding')
    })

    test('OTP accepts a pasted code and resend uses the available fallback channel', async ({
      page,
    }) => {
      const calls = await mockOnboarding(page, 0)
      await page.goto(`${origin}/facility-onboarding`)
      await page
        .getByRole('button', { name: /Start secure onboarding/ })
        .click()
      await page.getByPlaceholder('Enter your ID number').fill('12345678')
      await page.getByRole('button', { name: 'Find my facilities' }).click()
      await page.getByLabel(/Verification code: 1 \/ 6/).focus()
      await page.evaluate(() => {
        const data = new DataTransfer()
        data.setData('text', '12 34-56')
        document.activeElement!.dispatchEvent(
          new ClipboardEvent('paste', {
            clipboardData: data,
            bubbles: true,
            cancelable: true,
          }),
        )
      })
      await expect(page.getByLabel(/Verification code: 6 \/ 6/)).toHaveValue(
        '6',
      )
      await expect(
        page.getByRole('button', { name: 'Verify and continue' }),
      ).toBeEnabled()
      await page.getByRole('button', { name: 'Resend code' }).click()
      await expect(
        page.getByText(/If your details match our records/),
      ).toBeVisible()
      expect(calls).toContain('resend_otp')
      await shot(page, `${vp.name}-onboarding-9-resend-sms`)
    })
  })
}

function portalState() {
  const state = {
    orders: [] as Record<string, unknown>[],
    invoices: [] as Record<string, unknown>[],
    paid: false,
  }
  const ois = () => ({
    name: 'OIS-2026-00001',
    status: 'Processed',
    network_slug: 'net-a',
    progress: {
      next_action: { label: 'Complete signatures' },
      contract: { required: 4, signed: 2 },
      steps: [
        { key: 'opt_in', label: 'Opt-In', status: 'complete' },
        { key: 'contract', label: 'Contract', status: 'current' },
        { key: 'signatures', label: 'Signatures', status: 'current' },
        { key: 'membership', label: 'Membership', status: 'upcoming' },
        { key: 'golive', label: 'GoLive', status: 'upcoming' },
      ],
      facilities: [
        {
          mfl_code: '10001',
          facility_name: 'Alpha Community Clinic',
          membership_status: 'Opted In',
          network_contact: { go_live: false },
        },
        {
          mfl_code: '10002',
          facility_name: 'Bravo Family Hospital With A Deliberately Long Name',
          membership_status: 'Active',
          network_contact: { go_live: false },
        },
      ],
    },
    open_orders: state.orders,
    open_invoices: state.invoices,
  })
  return { state, ois }
}

function selfOnboardedPortalState() {
  return {
    name: 'OIS-2026-00031',
    status: 'Processed',
    onboarding_source: 'token_self_onboarding',
    network_slug: 'Example Health Network',
    progress: {
      next_action: { label: 'Create an invoice for your token order' },
      package: {
        item_code: 'TOK-CORE',
        display_name: 'Core care operations',
        token_quantity: 100,
      },
      payment_status: 'Not started',
      steps: [
        { key: 'identity', label: 'Identity verified', status: 'complete' },
        { key: 'facility', label: 'Facilities confirmed', status: 'complete' },
        { key: 'optin', label: 'Opt-In submitted', status: 'complete' },
        { key: 'package', label: 'Token package selected', status: 'complete' },
        { key: 'order', label: 'Quote and order ready', status: 'complete' },
        { key: 'payment', label: 'Payment', status: 'current' },
        { key: 'golive', label: 'GoLive', status: 'locked' },
      ],
      facilities: [
        {
          mfl_code: '10001',
          facility_name: 'Alpha Community Clinic',
          membership_status: 'Active',
          network_contact: { go_live: false },
        },
      ],
      orders: [
        {
          name: 'SAL-ORD-2026-00031',
          grand_total: 34800,
          currency: 'KES',
          status: 'To Deliver and Bill',
          can_create_invoice: true,
          crm_token_facility_mfl: '10001',
          crm_token_package_item: 'TOK-CORE',
        },
      ],
      invoices: [],
    },
    open_orders: [
      {
        name: 'SAL-ORD-2026-00031',
        grand_total: 34800,
        currency: 'KES',
        status: 'To Deliver and Bill',
        can_create_invoice: true,
        crm_token_facility_mfl: '10001',
        crm_token_package_item: 'TOK-CORE',
      },
    ],
    open_invoices: [],
  }
}

for (const vp of VIEWPORTS) {
  test.describe(`customer portal (${vp.name})`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height } })

    test('resume order, confirm invoice creation, then authorised checkout and return verification', async ({
      page,
    }) => {
      const { state, ois } = portalState()
      const calls: string[] = []
      await page.route('**/api/method/**', async (route) => {
        const method = route
          .request()
          .url()
          .split('/api/method/')[1]
          .split('?')[0]
        const body = route.request().postDataJSON?.() || {}
        calls.push(method)
        if (method === 'crm.api.website_redirect.get_portal_context')
          return ok(route, {
            success: true,
            data: {
              route: '/cx-portal',
              user: 'owner@example.com',
              ois: [ois()],
              token_packages: PACKAGES,
            },
          })
        if (method === 'crm.api.customer_experience.create_token_order') {
          const existing = state.orders.find(
            (o) =>
              o.crm_token_facility_mfl === body.facility_mfl &&
              o.crm_token_package_item === body.package_item_code,
          )
          if (!existing)
            state.orders.push({
              name: 'SAL-ORD-2026-00001',
              grand_total: 34800,
              currency: 'KES',
              status: 'To Deliver and Bill',
              can_create_invoice: true,
              crm_token_facility_mfl: body.facility_mfl,
              crm_token_package_item: body.package_item_code,
            })
          return ok(route, {
            success: true,
            data: {
              sales_order: 'SAL-ORD-2026-00001',
              quotation: 'QTN-1',
              idempotent: !!existing,
            },
          })
        }
        if (method === 'crm.api.customer_experience.start_token_payment') {
          state.orders.length = 0
          state.invoices.push({
            name: 'ACC-SINV-2026-00001',
            invoice_number: 'ACC-SINV-2026-00001',
            due_date: '2099-01-01',
            amount: 34800,
            currency: 'KES',
          })
          return ok(route, {
            success: true,
            data: {
              invoice: 'ACC-SINV-2026-00001',
              ois: 'OIS-2026-00001',
              idempotent: false,
            },
          })
        }
        if (method === 'crm.api.checkout.initialize_portal_paystack_payment') {
          expect(body).toEqual({
            ois_number: 'OIS-2026-00001',
            invoice: 'ACC-SINV-2026-00001',
          })
          return ok(route, {
            authorization_url: `${origin}/__paystack__?x=1`,
            reference: 'OIS-OIS-2026-00001-ACC-SINV-2026-00001-ab12cd',
          })
        }
        if (method === 'crm.api.checkout.verify_portal_paystack_payment') {
          state.invoices.length = 0
          state.paid = true
          return ok(route, { paid: true, payment_entry: 'ACC-PAY-1' })
        }
        return route.fulfill({ status: 404 })
      })

      await page.goto(`${origin}/cx-portal`)
      await expect(page.getByText('Your facility journey')).toBeVisible()
      await expect(page.getByText(/Total\s+\S*\s*34,800/).first()).toBeVisible()
      await shot(page, `${vp.name}-portal-1-overview`)

      await page.getByRole('button', { name: 'Create order' }).first().click()
      await expect(
        page.getByText(/Order SAL-ORD-2026-00001 is ready/),
      ).toBeVisible()
      await expect(
        page.getByRole('button', { name: /Resume order SAL-ORD-2026-00001/ }),
      ).toBeVisible()
      await shot(page, `${vp.name}-portal-2-order-created`)

      // Retrying resumes the same order instead of creating another.
      await page
        .getByRole('button', { name: /Resume order/ })
        .first()
        .click()
      await expect(page.getByText(/is ready \(resumed\)/)).toBeVisible()
      expect(state.orders).toHaveLength(1)

      expect(calls).not.toContain(
        'crm.api.customer_experience.start_token_payment',
      )
      await page.getByRole('button', { name: 'Create invoice' }).click()
      await expect(page.getByText(/Your invoice is ready/)).toBeVisible()
      await expect(
        page.getByRole('button', { name: /Make payment/ }),
      ).toBeVisible()
      await shot(page, `${vp.name}-portal-4-invoice-open`)

      await page.getByRole('button', { name: /Make payment/ }).click()
      await expect(
        page.getByText('Paystack sandbox checkout (mock)'),
      ).toBeVisible()

      await page.goto(
        `${origin}/cx-portal?reference=OIS-OIS-2026-00001-ACC-SINV-2026-00001-ab12cd`,
      )
      await expect(page.getByText('Payment received. Thank you.')).toBeVisible()
      await expect(
        page.getByRole('button', { name: /Make payment/ }),
      ).toHaveCount(0)
      await shot(page, `${vp.name}-portal-5-paid`)
      expect(page.url()).not.toContain('reference=')
    })

    test('self-onboarded progress shows package, order, payment and service activation without signature steps', async ({
      page,
    }) => {
      await page.route(
        '**/api/method/crm.api.website_redirect.get_portal_context',
        async (route) =>
          ok(route, {
            success: true,
            data: {
              route: '/cx-portal',
              user: 'sam@example.com',
              ois: [selfOnboardedPortalState()],
              token_packages: PACKAGES,
            },
          }),
      )
      await page.goto(`${origin}/cx-portal`)
      await expect(page.getByText('Your facility journey')).toBeVisible()
      for (const milestone of [
        'Identity verified',
        'Facilities confirmed',
        'Opt-In submitted',
        'Token package selected',
        'Quote and order ready',
        'Payment',
        'Service activation',
      ])
        await expect(page.getByText(milestone, { exact: true })).toBeVisible()
      await expect(
        page.getByText('Selected package: Core care operations.', {
          exact: true,
        }),
      ).toBeVisible()
      await expect(
        page.getByRole('button', { name: 'Create invoice' }),
      ).toBeVisible()
      await expect(
        page.getByRole('button', { name: /Resume order SAL-ORD-2026-00031/ }),
      ).toBeVisible()
      await expect(page.locator('body')).not.toContainText(
        /signature|contract/i,
      )
      await shot(page, `${vp.name}-portal-self-onboarding-progress`)
    })

    test('held and closed orders do not offer invoice creation', async ({
      page,
    }) => {
      const submission = selfOnboardedPortalState()
      submission.open_orders[0].status = 'On Hold'
      submission.open_orders[0].can_create_invoice = false
      submission.open_orders.push({
        ...submission.open_orders[0],
        name: 'SAL-ORD-2026-00032',
        status: 'Closed',
      })
      await page.route(
        '**/api/method/crm.api.website_redirect.get_portal_context',
        async (route) =>
          ok(route, {
            success: true,
            data: {
              route: '/cx-portal',
              user: 'sam@example.com',
              ois: [submission],
              token_packages: PACKAGES,
            },
          }),
      )
      await page.goto(`${origin}/cx-portal`)
      await expect(
        page.getByText('This order is on hold. Contact support if you need help.'),
      ).toBeVisible()
      await expect(
        page.getByText('This order is closed and cannot be invoiced.'),
      ).toBeVisible()
      await expect(
        page.getByRole('button', { name: 'Create invoice' }),
      ).toHaveCount(0)
      await expect(
        page.locator('[aria-label="Account overview"]'),
      ).toContainText(/Orders ready for invoicing\s*0/)
    })

    test('a reference for someone else’s OIS is never verified and an unconfigured gateway offers bank transfer', async ({
      page,
    }) => {
      const { state, ois } = portalState()
      state.invoices.push({
        name: 'ACC-SINV-2026-00002',
        invoice_number: 'ACC-SINV-2026-00002',
        due_date: '2020-01-01',
        amount: 100,
        currency: 'KES',
      })
      const calls: string[] = []
      await page.route('**/api/method/**', async (route) => {
        const method = route
          .request()
          .url()
          .split('/api/method/')[1]
          .split('?')[0]
        calls.push(method)
        if (method === 'crm.api.website_redirect.get_portal_context')
          return ok(route, {
            success: true,
            data: { ois: [ois()], token_packages: PACKAGES },
          })
        if (method === 'crm.api.checkout.initialize_portal_paystack_payment')
          return fail(
            route,
            'Paystack is not configured. Use bank transfer or contact finance.',
          )
        return route.fulfill({ status: 404 })
      })
      await page.goto(
        `${origin}/cx-portal?reference=OIS-OIS-2099-00099-ACC-SINV-1-ff`,
      )
      await expect(page.getByText('Your facility journey')).toBeVisible()
      expect(calls).not.toContain(
        'crm.api.checkout.verify_portal_paystack_payment',
      )
      await expect(page.getByText('Overdue')).toBeVisible()
      await page.getByRole('button', { name: /Make payment/ }).click()
      await expect(page.getByRole('alert')).toContainText('not configured')
      await expect(
        page.getByRole('link', { name: 'Other payment options' }),
      ).toBeVisible()
      await shot(page, `${vp.name}-portal-6-gateway-unavailable`)
    })
  })
}
