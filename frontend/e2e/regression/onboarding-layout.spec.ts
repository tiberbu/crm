import { mkdirSync } from 'fs'
import { join } from 'path'
import { expect, test, type Page } from '@playwright/test'
import type { Server } from 'http'
import { auditLayout, startPortalServer } from './portalFixture'

// Self-onboarding Facility, Package and Review steps (docs/cx-portal-token-alerts-and-ui-review.md,
// OB-1..OB-11): the built bundle with the onboarding API mocked, at every audit viewport.
const SHOTS = process.env.SCREENSHOT_DIR || ''
const TERMS = 'CareverseHIMS Value Express Terms'

let server: Server
let origin = ''
test.beforeAll(async () => ({ server, origin } = await startPortalServer()))
test.afterAll(() => server.close())

const facilities = [
  {
    facility_id: 'FID-00-OB-01',
    facility_name:
      'St. Elizabeth Comprehensive Maternal and Child Health Centre',
    mfl_code: 'OB-01',
    facility_level: 'Level 3',
    classification: 'Level 3',
    facility_type: 'Health Centre',
    onboarding_eligible: true,
  },
  {
    facility_id: 'FID-00-OB-02',
    facility_name: 'Mwangaza Community Dispensary',
    mfl_code: 'OB-02',
    facility_level: '',
    classification: '',
    facility_type: 'Dispensary',
    onboarding_eligible: true,
  },
  {
    facility_id: 'FID-00-OB-03',
    facility_name: 'Registry Gap Clinic',
    mfl_code: 'OB-03',
    facility_level: '',
    onboarding_eligible: false,
    facility_eligibility_reason: 'missing_level',
  },
]

const pkg = (
  code: string,
  name: string,
  tokens: number,
  price: number,
  extra: Record<string, unknown> = {},
) => ({
  item_code: code,
  display_name: name,
  description: `${name} package`,
  token_quantity: tokens,
  price_ex_vat: price,
  vat_amount: price * 0.16,
  gross_total: price * 1.16,
  vat_label: 'VAT (16%)',
  currency: 'KES',
  plan: 'Flex',
  ...extra,
})
const catalog = {
  network: {},
  packages: [
    pkg('STARTER', 'Starter', 1000, 6000, {
      audience: 'For small OPD clinics & pilots',
    }),
    pkg('GROWTH', 'Growth', 2800, 15000, {
      audience: 'For active & growing clinics',
      coverage_metrics: '{"badge": "Popular"}',
    }),
    pkg('SCALE', 'Scale', 6250, 30000),
  ],
  fixed_packages: [
    pkg('FIXED-L3', 'Fixed L3', 0, 18000, {
      plan: 'Fixed',
      facility_levels: ['Level 3'],
      billing_period: 'Monthly',
    }),
  ],
  custom_offer: {
    item_code: 'CUSTOM',
    display_name: 'Custom',
    currency: 'KES',
    min_tokens: 1000,
    min_amount: 6000,
    tiers: [
      { name: 'Starter', from_amount: 6000, rate: 6 },
      { name: 'Growth', from_amount: 15000, rate: 5.36 },
    ],
  },
  calculator_config: {},
  welcome_bonus_tokens: 0,
  partner_coupon_tokens: 0,
}

async function startOnboarding(page: Page) {
  const termsRequests: Record<string, unknown>[] = []
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
    const body =
      (route.request().postDataJSON?.() as Record<string, unknown>) || {}
    const answers: Record<string, unknown> = {
      start_identity: {
        session_token: 'session-1',
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
      get_catalog: { success: true, data: catalog },
      get_self_onboarding_terms: {
        document: TERMS,
        rendered_html:
          '<p>Total selected-term commitment (inclusive of VAT): KES 34,800.00</p>',
        content_hash: '0'.repeat(64),
      },
      check_onboarding_conflicts: { conflicts: [] },
    }
    if (method === 'get_self_onboarding_terms') termsRequests.push(body)
    return route.fulfill({
      json: { message: method && method in answers ? answers[method] : {} },
    })
  })
  await page.goto(`${origin}/facility-onboarding`)
  await page.getByPlaceholder('Enter your ID number').fill('12345678')
  await page.getByRole('button', { name: /Verify & Find My Facility/ }).click()
  await page.getByLabel(/1 \/ 6/).click()
  await page.keyboard.type('123456')
  await page
    .locator('form button:not([type]), form button[type=submit]')
    .first()
    .click()
    .catch(() => {})
  await expect(
    page.getByRole('heading', {
      name: 'Select the facility you want to onboard',
    }),
  ).toBeVisible()
  return termsRequests
}

async function check(page: Page, step: string, name: string) {
  if (SHOTS) {
    mkdirSync(SHOTS, { recursive: true })
    await page.screenshot({
      path: join(SHOTS, `${name}-onboarding-${step}.png`),
      fullPage: true,
    })
  }
  const issues = await auditLayout(page)
  expect(issues, `${step}: ${JSON.stringify(issues, null, 1)}`).toEqual([])
}

test('facility, package and review steps follow the review fixes and lay out cleanly', async ({
  page,
}, info) => {
  const termsRequests = await startOnboarding(page)
  const name = info.project.name

  // OB-1: a selectable facility without a level says what happens next; a blocked one says why.
  await expect(page.getByTestId('facility-level-missing')).toContainText(
    'our team confirms the level before go-live',
  )
  await expect(
    page.getByText(
      'The registry has no KEPH level for this facility, and Value Express is priced by level',
    ),
  ).toBeVisible()
  await check(page, 'facility', name)

  for (const box of await page.getByTestId('facility-select-checkbox').all())
    await box.check()
  await page.getByRole('button', { name: /Continue to Packages/ }).click()
  await expect(page.getByTestId('package-grid')).toBeVisible()

  // OB-9 heading, OB-3 Suits only where the package has one, OB-8 badge text.
  await expect(
    page.getByRole('heading', { name: 'Value Express Flex: pay as you use' }),
  ).toBeVisible()
  const cards = page.getByTestId('package-grid').locator('.pkg')
  const card = (title: string) =>
    cards.filter({
      has: page.locator('.nm', { hasText: new RegExp(`^${title}$`) }),
    })
  await expect(card('Starter')).toContainText('For small OPD clinics & pilots')
  await expect(card('Scale')).not.toContainText('Suits')
  await expect(card('Growth').locator('.rec')).toHaveText('Popular')

  // OB-7: the coupon panel opens in the page flow, below the facility tabs, with one action.
  await page.getByTestId('partner-coupon-toggle').click()
  const panel = page.locator('#partner-coupon-panel')
  const tabs = page.locator('.factabs')
  const [panelBox, tabsBox] = [
    await panel.boundingBox(),
    await tabs.boundingBox(),
  ]
  expect(panelBox!.y + panelBox!.height).toBeLessThanOrEqual(tabsBox!.y + 1)
  await expect(panel.getByRole('button')).toHaveCount(1)
  await panel.getByRole('button').click()
  await expect(panel).toHaveCount(0)

  // OB-4: a Custom amount that is not a whole number of tokens explains the charge.
  await page.locator('#custom-amount').fill('7000')
  await expect(page.getByTestId('custom-charge')).toHaveText('KES 6,996.00')
  await expect(page.getByTestId('custom-rounding')).toContainText(
    '1,166 whole tokens',
  )
  await check(page, 'package', name)

  // OB-2: Back returns to the Facility step with the selection kept.
  await page.getByTestId('pricing-back').click()
  await expect(
    page.getByRole('heading', {
      name: 'Select the facility you want to onboard',
    }),
  ).toBeVisible()
  await expect(
    page.getByTestId('facility-select-checkbox').first(),
  ).toBeChecked()
  await page.getByRole('button', { name: /Continue to Packages/ }).click()

  // Choose a package for each facility (OB-6: Fixed lists what is included).
  await page.getByTestId('plan-fixed').click()
  await expect(
    page.getByRole('heading', { name: 'What’s included' }),
  ).toBeVisible()
  await page.getByTestId('plan-flex').click()
  await card('Scale')
    .getByRole('button', { name: /Select Scale/ })
    .click()
  await page.getByRole('button', { name: /^Next:/ }).click()
  await card('Growth')
    .getByRole('button', { name: /Select Growth/ })
    .click()
  await page
    .locator('.sumbar')
    .getByRole('button', { name: /Continue to Review/ })
    .click()
  await expect(page.getByTestId('self-onboarding-terms')).toBeVisible()

  // OB-10: the Terms are requested for the chosen packages; OB-11: one name throughout.
  expect(
    JSON.parse(String(termsRequests.at(-1)!.facility_package_items)),
  ).toEqual({ 'FID-00-OB-01': 'SCALE', 'FID-00-OB-02': 'GROWTH' })
  await expect(page.locator('#review-terms-title')).toHaveText(TERMS)
  await expect(page.getByTestId('terms-open')).toHaveText(TERMS)
  await page.getByTestId('terms-open').click()
  await expect(page.getByRole('dialog')).toContainText(TERMS)
  await expect(page.getByRole('dialog')).toContainText('KES 34,800.00')
  await page.keyboard.press('Escape')
  await check(page, 'review', name)

  // OB-2: the stepper reopens a completed step.
  await page.getByTestId('step-facilities').click()
  await expect(
    page.getByRole('heading', {
      name: 'Select the facility you want to onboard',
    }),
  ).toBeVisible()
})
