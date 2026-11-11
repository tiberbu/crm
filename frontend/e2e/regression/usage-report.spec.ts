import { mkdirSync } from 'fs'
import { join } from 'path'
import { expect, test, type Page } from '@playwright/test'
import type { Server } from 'http'
import {
  auditLayout,
  mockPortalApi,
  openView,
  portalContext,
  sampleTypography,
  startPortalServer,
  stressFacilities,
} from './portalFixture'

// Facility token usage report (P-135): the Usage tab on a token facility, its date range,
// the reconciliation cards, the billing-event breakdown, the price check and the CSV
// download, with the layout and brand type gates. Frappe's API is mocked; the backend
// contract is covered by crm/tests/test_usage_report.py and the mediator's tests.
const SHOTS = process.env.SCREENSHOT_DIR || ''
const WEIGHTS = new Set([400, 420, 500, 600])
const BRAND = 'rgb(188, 24, 35)'
const facility = stressFacilities[0]
const noFid = stressFacilities[2]

let server: Server
let origin = ''
test.beforeAll(async () => ({ server, origin } = await startPortalServer()))
test.afterAll(() => server.close())

function report(from: string, to: string) {
  const event = (
    id: string,
    name: string,
    label: string,
    qty: number,
    unit: number,
    tokens: number,
    check: string,
    price: number,
  ) => ({
    time: `${to} 09:${id.slice(-2)}:00`,
    event_id: id,
    billing_event: name,
    label,
    quantity: qty,
    unit_tokens: unit,
    tokens,
    expected_tokens: qty * unit,
    current_price: price,
    catalog_version: '1',
    check,
  })
  return {
    status: 'ok',
    fid: facility.hfr_facility_id,
    from_date: from,
    to_date: to,
    time_zone: 'Africa/Nairobi',
    generated_at: `${to} 10:00:00`,
    detail: {
      available: true,
      from: `${from} 00:00:00`,
      complete: true,
      truncated: false,
      max_events: 5000,
      window_days: 30,
    },
    summary: {
      tokens_added: {
        in_range: { total: 1500, by_source: { paid: 1000, bonus: 500 } },
        all_time: 3500,
        rows: [],
      },
      tokens_consumed: 1284,
      balance: 120,
      patient_registrations: { value: 212, estimated: false },
      consultations: { value: 118, estimated: false },
      checks: { matches: 61, price_differs: 1, charge_differs: 1 },
    },
    breakdown: [
      {
        billing_event: 'consultation',
        label: 'Clinician consultation',
        category: 'Clinical',
        current_price: 5,
        quantity: 118,
        quantity_estimated: false,
        tokens: 590,
        share: 0.4595,
      },
      {
        billing_event: 'patient_registration',
        label: 'Patient registration',
        category: 'Front office',
        current_price: 3,
        quantity: 212,
        quantity_estimated: false,
        tokens: 636,
        share: 0.4953,
      },
      {
        billing_event: 'Consultation',
        label: 'Consultation',
        category: '',
        current_price: null,
        quantity: 116,
        quantity_estimated: false,
        tokens: 58,
        share: 0.0452,
      },
    ],
    daily: [
      { date: from, tokens: 640, by_event: {} },
      { date: to, tokens: 644, by_event: {} },
    ],
    events: [
      event(
        'REG-0001',
        'patient_registration',
        'Patient registration',
        1,
        4,
        4,
        'price_differs',
        3,
      ),
      event(
        'CON-0002',
        'consultation',
        'Clinician consultation',
        2,
        5,
        5,
        'charge_differs',
        5,
      ),
      ...Array.from({ length: 60 }, (_, i) =>
        event(
          `REG-1${String(i).padStart(3, '0')}`,
          'patient_registration',
          'Patient registration',
          1,
          3,
          3,
          'matches',
          3,
        ),
      ),
    ],
  }
}

async function openUsage(page: Page) {
  const calls: Record<string, unknown>[] = []
  await mockPortalApi(page, portalContext(), async (method, body, route) => {
    if (method === 'crm.api.usage_report.get_facility_usage_report') {
      calls.push(body)
      await route.fulfill({
        json: { message: report(String(body.from_date), String(body.to_date)) },
      })
      return true
    }
  })
  await page.goto(`${origin}/cx-portal`)
  await openView(page, 'facilities')
  await page
    .getByRole('button', { name: facility.facility_name })
    .first()
    .click()
  await expect(
    page.getByRole('heading', { name: facility.facility_name, level: 1 }),
  ).toBeVisible()
  await page.getByTestId('facility-tab-usage').click()
  await expect(page.getByTestId('usage-summary')).toBeVisible()
  return calls
}

async function brandGates(page: Page) {
  const issues = await auditLayout(page)
  expect(issues, JSON.stringify(issues, null, 1)).toEqual([])
  const samples = await sampleTypography(page)
  const heavy = samples
    .filter((s) => !WEIGHTS.has(s.weight))
    .map((s) => `${s.weight} "${s.text}"`)
  const tiny = samples
    .filter((s) => s.size < 11)
    .map((s) => `${s.size}px "${s.text}"`)
  const lowContrast = samples
    .filter((s) => s.ratio < s.required)
    .map((s) => `${s.ratio}:1 "${s.text}"`)
  expect({ heavy, tiny, lowContrast }).toEqual({
    heavy: [],
    tiny: [],
    lowContrast: [],
  })
}

test('owner sees usage for the last 30 days, reconciles it and can download it', async ({
  page,
}, info) => {
  const calls = await openUsage(page)
  expect(calls[0]).toMatchObject({ mfl_code: facility.mfl_code })
  const usage = page.getByTestId('usage-report')
  await expect(usage).toContainText(facility.hfr_facility_id)
  await expect(page.getByTestId('usage-preset-last30')).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await expect(page.getByTestId('usage-card-added')).toContainText('1,500')
  await expect(page.getByTestId('usage-card-added')).toContainText(
    '3,500 since onboarding',
  )
  await expect(page.getByTestId('usage-card-consumed')).toContainText('1,284')
  await expect(page.getByTestId('usage-card-balance')).toContainText('120')
  await expect(page.getByTestId('usage-card-registrations')).toContainText(
    '212',
  )
  await expect(page.getByTestId('usage-added-sources')).toContainText(
    '1,000 paid tokens',
  )
  await expect(page.getByTestId('usage-breakdown')).toContainText(
    'Clinician consultation',
  )
  await expect(page.getByTestId('usage-check-price_differs')).toContainText(
    '1 · Price differs from current list',
  )
  await expect(page.getByTestId('usage-check-charge_differs')).toContainText(
    'Charge differs',
  )
  // 62 events, 50 shown, then the rest on request.
  await expect(page.getByTestId('usage-event-row')).toHaveCount(50)
  await page.getByTestId('usage-more-events').click()
  await expect(page.getByTestId('usage-event-row')).toHaveCount(62)
  await page.getByTestId('usage-only-flagged').check()
  await expect(page.getByTestId('usage-event-row')).toHaveCount(2)

  const download = page.getByTestId('usage-download')
  await expect(download).toHaveAttribute(
    'href',
    new RegExp(
      `download_facility_usage_report\\?mfl_code=${facility.mfl_code}&from_date=\\d{4}-\\d{2}-\\d{2}&to_date=`,
    ),
  )
  await expect(download).toHaveCSS('background-color', BRAND)
  if (SHOTS) {
    mkdirSync(SHOTS, { recursive: true })
    await page.screenshot({
      path: join(SHOTS, `${info.project.name}-facility-usage.png`),
      fullPage: true,
    })
  }
  await brandGates(page)
})

test('a preset or custom range reloads the report and a bad range is refused', async ({
  page,
}) => {
  const calls = await openUsage(page)
  await page.getByTestId('usage-preset-last7').click()
  await expect.poll(() => calls.length).toBe(2)
  expect(calls[1].from_date).not.toEqual(calls[0].from_date)

  await page.getByTestId('usage-from').fill('2026-11-10')
  await page.getByTestId('usage-to').fill('2026-11-01')
  await expect(page.getByRole('alert')).toContainText(
    'on or after the start date',
  )
  await expect(page.getByTestId('usage-apply')).toBeDisabled()
  // Unapplied edits never change what the download contains.
  await expect(page.getByTestId('usage-download')).toHaveAttribute(
    'href',
    new RegExp(`from_date=${calls[1].from_date}&to_date=${calls[1].to_date}`),
  )

  await page.getByTestId('usage-to').fill('2026-11-10')
  await page.getByTestId('usage-apply').click()
  await expect.poll(() => calls.length).toBe(3)
  expect(calls[2]).toMatchObject({
    from_date: '2026-11-10',
    to_date: '2026-11-10',
  })
})

test('a facility without a Facility ID has no Usage tab', async ({ page }) => {
  await mockPortalApi(page, portalContext())
  await page.goto(`${origin}/cx-portal`)
  await openView(page, 'facilities')
  await page.getByRole('button', { name: noFid.facility_name }).first().click()
  await expect(
    page.getByRole('heading', { name: noFid.facility_name, level: 1 }),
  ).toBeVisible()
  await expect(page.getByTestId('facility-tab-overview')).toBeVisible()
  await expect(page.getByTestId('facility-tab-usage')).toHaveCount(0)
})
