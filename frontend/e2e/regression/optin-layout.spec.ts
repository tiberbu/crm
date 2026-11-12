import { mkdirSync } from 'fs'
import { join } from 'path'
import { expect, test, type Page } from '@playwright/test'
import type { Server } from 'http'
import { startPortalServer } from './portalFixture'

// Network opt-in quotation step on desktop and laptop Chrome: the wizard card is a fixed
// narrow column, so its grids must not switch to viewport-wide column counts. Every text
// box has to stay inside its card, with the largest realistic amounts (multi-facility,
// five-year terms) and long optional-service names. Covers the pricing, review and
// facility steps; phone and tablet run the same assertions.
const SHOTS = process.env.SCREENSHOT_DIR || ''

let server: Server
let origin = ''
test.beforeAll(async () => ({ server, origin } = await startPortalServer()))
test.afterAll(() => server.close())

const facilities = Array.from({ length: 4 }, (_, i) => ({
  facility_name: `Synthetic County Referral Hospital Number ${i + 1}`,
  mfl_code: `SYN-0${i + 1}`,
  keph_level: String(4 + (i % 2)),
  facility_id: `FID-00-SYN-0${i + 1}`,
  monthly_kes: 1234567.89,
  annual_kes: 14814814.68,
}))

const plan = (year: number) => ({
  year_number: year,
  label: `Year ${year}`,
  grand_total_annual: 68740740.12 + year,
  grand_total_monthly: 5728395.01,
  subtotal_annual: 59259258.72,
  subtotal_monthly: 4938271.56,
  vat_annual: 9481481.4,
  vat_monthly: 790123.45,
  facilities,
  first_invoice_relative_label: 'about 90 days after submission',
  invoice_schedule_anchor_label: 'projected from submission date',
  invoice_schedule: [1, 2, 3, 4].map((q) => ({
    billing_key: `y${year}q${q}`,
    quarter_number: q,
    period_label: `Quarter ${q}`,
    amount_incl_vat: 17185185.03,
    amount_excl_vat: 14814814.68,
    invoice_date: '2027-09-30',
    invoice_due_date: '2027-10-30',
  })),
})
const plans = [1, 2, 3, 4, 5].map(plan)

const optionalServices = [
  {
    item_code: 'SYN-IMPL-ENT',
    item_name: 'Synthetic HMIS Implementation &amp; Training — Enterprise',
    description: 'Synthetic HMIS Implementation &amp; Training — Enterprise',
  },
  {
    item_code: 'SYN-HW-WS',
    item_name: 'Endpoint Workstation — Synthetic Model 7010 MT with 27" display',
    description:
      '<div><p>Recommended for front-desk and pharmacy counters with heavy daily throughput.</p></div>',
  },
  {
    item_code: 'SYN-SVC-ENGINEER',
    item_name: 'On-Site Support Engineer (5 days/wk)',
    description: 'Supersupportengineeringcoverageforallwardsandoutpatientclinicsincludedwithoutspaces',
  },
]

async function openWizard(page: Page) {
  await page.route('**/api/method/**', (route) => {
    const method = route.request().url().split('/api/method/')[1].split('?')[0]
    if (method === 'crm.api.optin.get_settings')
      return route.fulfill({
        json: {
          message: {
            network_config: { display_name: 'Synthetic Network', logo_url: '', primary_colour: null },
            price_plans: plans.map(({ year_number, label }) => ({ year_number, label })),
            optional_services: optionalServices,
          },
        },
      })
    return route.fulfill({ json: { message: {} } })
  })
  await page.goto(`${origin}/opt-in?network=synthetic-network`)
  await expect(page.getByRole('heading', { name: 'Synthetic Network' })).toBeVisible()
}

async function setStep(page: Page, patch: Record<string, unknown>) {
  await page.evaluate((p) => {
    const el = document.querySelector('#optin-app') as unknown as {
      __vue_app__: { config: { globalProperties: { $pinia: { _s: Map<string, { $patch: (x: unknown) => void }> } } } }
    }
    el.__vue_app__.config.globalProperties.$pinia._s.get('optin')!.$patch(p)
  }, patch)
  await page.waitForTimeout(300)
}

type Spill = { text: string; box: string; overBy: number }

// A text element spills when it pokes out of the nearest bordered card around it, or when
// its own content is wider than its box. Scroll containers (the pricing table) are allowed
// to hold wider content: they scroll instead of spilling.
async function spills(page: Page): Promise<Spill[]> {
  return page.evaluate(() => {
    const root = document.querySelector('#optin-app')!
    const out: { text: string; box: string; overBy: number }[] = []
    const scrolls = (el: Element) => /(auto|scroll)/.test(getComputedStyle(el).overflowX)
    const card = (el: Element) => {
      const cs = getComputedStyle(el)
      return parseFloat(cs.borderTopWidth) > 0 && parseFloat(cs.borderTopLeftRadius) > 0
    }
    for (const el of Array.from(root.querySelectorAll('*'))) {
      const own = Array.from(el.childNodes)
        .filter((n) => n.nodeType === Node.TEXT_NODE)
        .map((n) => n.textContent?.trim() || '')
        .join(' ')
        .trim()
      if (!own) continue
      const rect = el.getBoundingClientRect()
      if (!rect.width) continue
      if (el.scrollWidth > el.clientWidth + 1 && !scrolls(el) && el.clientWidth > 0)
        out.push({ text: own.slice(0, 60), box: 'own box', overBy: el.scrollWidth - el.clientWidth })
      let parent = el.parentElement
      while (parent && parent !== root) {
        if (scrolls(parent)) break
        if (card(parent)) {
          const p = parent.getBoundingClientRect()
          const overBy = Math.max(rect.right - p.right, p.left - rect.left)
          if (overBy > 1) out.push({ text: own.slice(0, 60), box: parent.className.slice(0, 60), overBy })
          break
        }
        parent = parent.parentElement
      }
    }
    return out
  })
}

test('the quotation step keeps every amount and service name inside its card', async ({ page }, info) => {
  await openWizard(page)
  await setStep(page, {
    step: 3,
    selectedFacilities: facilities,
    pricing: { ...plans[0], plans, selected_years: [1, 2, 3, 4, 5], commitment_annual: 343703715.6, commitment_net_annual: 296296293.6, optional_services: optionalServices },
  })
  await expect(page.getByText('Optional services and hardware')).toBeVisible()
  // Open a year's invoice breakdown so the quarterly cards render too.
  await page.getByRole('button', { name: 'View invoice breakdown' }).first().click()
  await expect(page.getByText('Year 1 invoice breakdown')).toBeVisible()

  // Service names and descriptions are shown as text, never as escaped HTML, and a
  // description that repeats the name is not shown twice.
  await expect(page.getByText('Synthetic HMIS Implementation & Training — Enterprise')).toHaveCount(1)
  await expect(page.getByText('&amp;')).toHaveCount(0)
  await expect(page.getByText('<div>')).toHaveCount(0)
  await expect(page.getByText('Recommended for front-desk and pharmacy counters', { exact: false })).toBeVisible()

  if (SHOTS) {
    mkdirSync(SHOTS, { recursive: true })
    await page.screenshot({ path: join(SHOTS, `optin-layout-pricing-${info.project.name}.png`), fullPage: true })
  }
  expect(await spills(page)).toEqual([])

  // Lenovo E14-class laptops in Chrome (1920×1080 at 150%, or 1366×768 at 100%) leave a
  // short CSS viewport; the step must still fit its card and scroll to the footer.
  if (info.project.name === 'laptop') {
    for (const viewport of [
      { width: 1280, height: 631 },
      { width: 1366, height: 657 },
    ]) {
      await page.setViewportSize(viewport)
      await page.waitForTimeout(200)
      expect(await spills(page), `${viewport.width}×${viewport.height}`).toEqual([])
      const next = page.getByRole('button', { name: 'Back' })
      await next.scrollIntoViewIfNeeded()
      await expect(next).toBeInViewport()
    }
  }
})

test('the review step keeps yearly amounts inside their cards', async ({ page }, info) => {
  await openWizard(page)
  await setStep(page, {
    step: 4,
    selectedFacilities: facilities,
    contact: { first_name: 'Synthetic', last_name: 'Contact', email: 'contact@example.test', phone: '+254700000000' },
    pricing: { ...plans[0], plans, selected_years: [1, 2, 3, 4, 5], commitment_annual: 343703715.6, commitment_net_annual: 296296293.6 },
    optionalItems: [optionalServices[0]],
  })
  await expect(page.getByText('Yearly quotations')).toBeVisible()
  await expect(page.getByText('Synthetic HMIS Implementation & Training — Enterprise')).toBeVisible()
  await expect(page.getByText('&amp;')).toHaveCount(0)
  if (SHOTS) {
    mkdirSync(SHOTS, { recursive: true })
    await page.screenshot({ path: join(SHOTS, `optin-layout-review-${info.project.name}.png`), fullPage: true })
  }
  expect(await spills(page)).toEqual([])
})
