import { mkdirSync } from 'fs'
import { join } from 'path'
import { expect, test, type Page } from '@playwright/test'
import type { Server } from 'http'
import {
  auditLayout,
  mockPortalApi,
  portalContext,
  sampleTypography,
  startPortalServer,
} from './portalFixture'

// Opt-In billing ledger (spec P-124 to P-133): the Opt-In Requests page and the facility
// Payment schedule tab, with Frappe's API mocked. Covers the `[object Object]` network
// regression, first-view payment dates, paying ahead and the Pay hand-off, plus the
// layout and brand type gates at every viewport.
const SHOTS = process.env.SCREENSHOT_DIR || ''
const WEIGHTS = new Set([400, 420, 500, 600])
const OIS = 'OIS-E2E-0001'
const MFL = '20001'

let server: Server
let origin = ''
test.beforeAll(async () => ({ server, origin } = await startPortalServer()))
test.afterAll(() => server.close())

function period(year: number, quarter: number, extra: Record<string, unknown> = {}) {
  const month = String(1 + (quarter - 1) * 3).padStart(2, '0')
  return {
    billing_key: `${OIS}-Y${year}-Q${quarter}`,
    label: `Year ${year} · Q${quarter}`,
    year,
    quarter,
    scheduled_date: `${2026 + year}-${month}-30`,
    // Due 30 days after the invoice date, as the schedule sets it.
    due_date: new Date(Date.UTC(2026 + year, Number(month) - 1, 30 + 30)).toISOString().slice(0, 10),
    amount: 98922.24,
    state: 'scheduled',
    state_label: 'Scheduled',
    sales_order: '',
    sales_invoice: '',
    invoice_date: '',
    invoice_total: 0,
    outstanding: 0,
    payments: [],
    issued_early: false,
    issued_by: '',
    ...extra,
  }
}

function ledger(issued = 0) {
  const periods = [1, 2].flatMap((year) => [1, 2, 3, 4].map((q) => period(year, q)))
  periods[0] = period(1, 1, { sales_order: 'SAL-ORD-E2E-1', state: 'order_ready', state_label: 'Order ready' })
  for (let i = 0; i < issued; i += 1) {
    Object.assign(periods[i], {
      state: 'due',
      state_label: 'Due',
      sales_order: periods[i].sales_order || `SAL-ORD-E2E-${i + 1}`,
      sales_invoice: `ACC-SINV-E2E-${i + 1}`,
      invoice_date: '2026-11-10',
      invoice_total: 98922.24,
      outstanding: 98922,
      issued_early: true,
      issued_by: 'customer',
    })
  }
  const remaining = periods.filter((row) => !row.sales_invoice)
  return {
    ois: OIS,
    network: 'Example Partner Health Network',
    contract: 'CONT-E2E-1',
    contract_status: 'Fully Executed',
    status: 'Processed',
    currency: 'KES',
    today: '2026-11-10',
    summary: {
      contract_total: 791377.92,
      invoiced_total: issued * 98922.24,
      paid_total: 0,
      outstanding_total: issued * 98922,
      overdue_total: 0,
      paid_ahead_total: 0,
      next_payment: issued
        ? { label: 'Year 1 · Q1', date: '2027-03-01', amount: 98922, state: 'due', sales_invoice: 'ACC-SINV-E2E-1' }
        : { label: 'Year 1 · Q1', date: '2027-01-30', amount: 98922.24, state: 'order_ready', sales_invoice: '' },
    },
    advance: {
      allowed: true,
      reason: '',
      max_periods: Math.min(4, 4 - issued),
      remaining: remaining.length,
      next: remaining.slice(0, 4).map((row) => ({ billing_key: row.billing_key, label: row.label, amount: row.amount })),
    },
    years: [1, 2].map((year) => ({
      year,
      quotation: { name: `SAL-QTN-E2E-${year}`, year, status_label: 'Accepted', amount: 395688.95 },
      periods: periods.filter((row) => row.year === year),
    })),
    quotes: [1, 2].map((year) => ({ name: `SAL-QTN-E2E-${year}`, year, status_label: 'Accepted', amount: 395688.95, currency: 'KES' })),
    other_invoices: [],
  }
}

function optinContext() {
  const context = portalContext()
  context.ois = [
    {
      name: OIS,
      status: 'Processed',
      network_slug: 'example-partner',
      // The record the `[object Object]` regression came from.
      network: { name: 'example-partner', display_name: 'Example Partner Health Network', coordinators: [] },
      facility_signatory_name: 'Example Signatory With A Long Name',
      contract: 'CONT-E2E-1',
      quote_names_json: JSON.stringify(['SAL-QTN-E2E-1', 'SAL-QTN-E2E-2']),
      open_orders: [],
      open_invoices: [],
      progress: {
        facilities: [
          {
            facility_name: 'Example Opt-In Medical Centre And Maternity Home',
            mfl_code: MFL,
            hfr_facility_id: 'FID-E2E-20001',
            commercial: {
              journey: 'network_optin',
              journey_label: 'Network Opt-In',
              plan_type: 'time_bound',
              has_tokens: false,
              plan: { name: 'Network subscription', ois: OIS, status: 'Active', schedule: [] },
              quotes: [
                { name: 'SAL-QTN-E2E-1', label: 'Year 1', status_label: 'Accepted', amount: 395688.95, currency: 'KES' },
              ],
            },
          },
        ],
      },
    },
  ] as never
  return context
}

async function openRequests(page: Page) {
  let issued = 0
  await mockPortalApi(page, optinContext(), (method, body, route) => {
    if (method === 'crm.api.optin_ledger.get_optin_ledger') {
      void route.fulfill({ json: { message: ledger(issued) } })
      return true
    }
    if (method === 'crm.api.optin_ledger.issue_optin_periods') {
      issued += Number(body.count) || 1
      const data = ledger(issued)
      void route.fulfill({
        json: {
          message: {
            issued: data.years[0].periods
              .filter((row) => row.sales_invoice)
              .map((row) => ({ billing_key: row.billing_key, label: row.label, sales_invoice: row.sales_invoice })),
            error: '',
            ledger: data,
          },
        },
      })
      return true
    }
    return false
  })
  await page.goto(`${origin}/cx-portal`)
  if ((page.viewportSize()?.width || 0) < 768) {
    const bar = page.getByRole('navigation', { name: 'Primary navigation' })
    await bar.getByRole('button', { name: 'More navigation options' }).click()
    await page.getByRole('button', { name: 'Opt-In Requests' }).filter({ visible: true }).first().click()
  } else {
    await page.getByRole('button', { name: /Opt-In Requests/ }).filter({ visible: true }).first().click()
  }
  await expect(page.getByTestId('ledger-summary')).toBeVisible()
}

async function brandGates(page: Page) {
  const issues = await auditLayout(page)
  expect(issues, JSON.stringify(issues, null, 1)).toEqual([])
  const samples = await sampleTypography(page)
  const heavy = samples.filter((s) => !WEIGHTS.has(s.weight)).map((s) => `${s.weight} "${s.text}"`)
  const tiny = samples.filter((s) => s.size < 11).map((s) => `${s.size}px "${s.text}"`)
  const lowContrast = samples.filter((s) => s.ratio < s.required).map((s) => `${s.ratio}:1 "${s.text}"`)
  expect({ heavy, tiny, lowContrast }).toEqual({ heavy: [], tiny: [], lowContrast: [] })
}

test('Opt-In Requests names the network and shows the schedule on first view', async ({ page }, info) => {
  await openRequests(page)
  const card = page.getByTestId(`optin-request-${OIS}`)
  await expect(card.getByTestId('optin-request-network')).toHaveText('Example Partner Health Network')
  await expect(card).not.toContainText('[object Object]')
  await expect(page.getByTestId('ledger-tile-contract')).toContainText('KES')
  await expect(page.getByTestId('ledger-next-payment')).toContainText('Year 1 · Q1')
  // Year 1 is open on first view, with dates, and its order is on the trail.
  await expect(page.getByTestId(`ledger-period-${OIS}-Y1-Q2`)).toContainText('Invoice on')
  await expect(page.getByTestId(`ledger-trail-${OIS}-Y1-Q1`)).toContainText('SAL-ORD-E2E-1')
  await expect(page.getByTestId('ledger-pay-ahead')).toContainText('Pay ahead of your schedule')
  // Quotes are links to the permission-checked PDF.
  await expect(page.getByTestId('ledger-quote-SAL-QTN-E2E-2')).toHaveAttribute(
    'href',
    /crm\.api\.optin_ledger\.quotation_pdf\?quotation=SAL-QTN-E2E-2&ois_number=OIS-E2E-0001/,
  )
  if (SHOTS) {
    mkdirSync(SHOTS, { recursive: true })
    await page.screenshot({ path: join(SHOTS, `${info.project.name}-optin-requests.png`), fullPage: true })
  }
  await brandGates(page)
})

test('paying ahead creates the chosen invoices and each one can be paid', async ({ page }, info) => {
  await openRequests(page)
  await page.getByTestId('ledger-count-plus').click()
  await expect(page.getByTestId('ledger-count')).toHaveText('2')
  await expect(page.getByTestId('ledger-advance-range')).toHaveText('Year 1 · Q1 – Year 1 · Q2')
  await expect(page.getByTestId('ledger-issue')).toContainText('Create 2 invoices')
  await page.getByTestId('ledger-issue').click()
  await expect(page.getByTestId('ledger-issued')).toContainText('ACC-SINV-E2E-2')
  await expect(page.getByTestId(`ledger-state-${OIS}-Y1-Q2`)).toHaveText('Due')
  await expect(page.getByTestId('ledger-tile-outstanding')).toContainText('197,844')
  if (SHOTS) await page.screenshot({ path: join(SHOTS, `${info.project.name}-optin-paid-ahead.png`), fullPage: true })
  await brandGates(page)
  await page.getByTestId(`ledger-pay-${OIS}-Y1-Q1`).click()
  await expect(page.getByText('ACC-SINV-E2E-1').filter({ visible: true }).last()).toBeVisible()
})

test('an Opt-In facility page has a Payment schedule tab and clickable quotes', async ({ page }, info) => {
  await openRequests(page)
  if ((page.viewportSize()?.width || 0) < 768) {
    await page.getByRole('navigation', { name: 'Primary navigation' }).getByRole('button', { name: 'Facilities', exact: true }).click()
  } else {
    await page.getByRole('button', { name: /^\s*Facilities/ }).filter({ visible: true }).first().click()
  }
  await page.getByRole('button', { name: 'Example Opt-In Medical Centre And Maternity Home' }).first().click()
  await page.getByTestId('facility-tab-schedule').click()
  await expect(page.getByTestId('facility-panel-schedule').getByTestId('ledger-schedule')).toBeVisible()
  await page.getByTestId('facility-tab-quote').click()
  await expect(page.getByTestId('facility-quote-link-SAL-QTN-E2E-1')).toHaveAttribute('href', /ois_number=OIS-E2E-0001/)
  if (SHOTS) await page.screenshot({ path: join(SHOTS, `${info.project.name}-optin-facility-quotes.png`), fullPage: true })
  await page.getByTestId('facility-tab-schedule').click()
  await expect(page.getByTestId('ledger-summary')).toBeVisible()
  if (SHOTS) await page.screenshot({ path: join(SHOTS, `${info.project.name}-optin-facility-schedule.png`), fullPage: true })
  await brandGates(page)
})
