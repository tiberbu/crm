import { mkdirSync } from 'fs'
import { join } from 'path'
import { expect, test, type Page } from '@playwright/test'
import type { Server } from 'http'
import { startPortalServer } from './portalFixture'

// Network opt-in journey (pre-qualified invitation → wizard) against the brand guide:
// docs/tiberbu-crm-centralized-theme-spec.md and docs/tiberbu-crm-typography-perf-spec.md.
// Brand red #bc1823, frappe-ui neutrals on a plain page, local InterVar, weights ≤ 600,
// and no CX Portal glass, gradients or off-brand tints.
const SHOTS = process.env.SCREENSHOT_DIR || ''
const BRAND_RGB = 'rgb(188, 24, 35)'

let server: Server
let origin = ''
test.beforeAll(async () => ({ server, origin } = await startPortalServer()))
test.afterAll(() => server.close())

const facilities = [
  { facility_name: 'Synthetic Clinic A', mfl_code: 'SYN-01', keph_level: '2', facility_id: '' },
  { facility_name: 'Synthetic Health Centre B', mfl_code: 'SYN-02', keph_level: '3', facility_id: 'FID-00-SYN-02' },
]

async function openWizard(page: Page, primaryColour: string | null = null) {
  await page.route('**/api/method/**', (route) => {
    const method = route.request().url().split('/api/method/')[1].split('?')[0]
    if (method === 'crm.api.optin.get_settings')
      return route.fulfill({
        json: {
          message: {
            network_config: {
              display_name: 'Synthetic Network',
              logo_url: '',
              primary_colour: primaryColour,
            },
            price_plans: [],
            optional_services: [],
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

type Violation = { rule: string; el: string; value: string }

// Every rendered element is checked against the brand guide rules.
async function brandViolations(page: Page): Promise<Violation[]> {
  return page.evaluate(() => {
    const out: { rule: string; el: string; value: string }[] = []
    const label = (el: Element) =>
      `${el.tagName.toLowerCase()}.${String((el as HTMLElement).className?.toString?.() || '').slice(0, 50)}`
    const rgb = (v: string) => (v.match(/[\d.]+/g) || []).map(Number)
    // Off-brand tints: CX Portal material (teal/emerald, slate canvas) and the retired
    // reds #C0101A and #b91c1c that the journey used before the brand guide red.
    const offBrand = (v: string) => {
      const [r, g, b, a = 1] = rgb(v)
      if (!v.startsWith('rgb') || a === 0) return false
      return (
        (r === 16 && g === 185 && b === 129) ||
        (r === 244 && g === 246 && b === 248) ||
        (r === 192 && g === 16 && b === 26) ||
        (r === 185 && g === 28 && b === 28)
      )
    }
    for (const el of Array.from(document.querySelectorAll('body *'))) {
      const s = getComputedStyle(el)
      const box = el.getBoundingClientRect()
      if (box.width === 0 || box.height === 0 || s.visibility === 'hidden') continue
      if (/gradient/.test(s.backgroundImage)) out.push({ rule: 'no-gradient', el: label(el), value: s.backgroundImage })
      if (s.backdropFilter && s.backdropFilter !== 'none')
        out.push({ rule: 'no-glass', el: label(el), value: s.backdropFilter })
      for (const k of ['color', 'backgroundColor', 'borderTopColor'] as const)
        if (offBrand(s[k])) out.push({ rule: 'off-brand-colour', el: label(el), value: `${k} ${s[k]}` })
      const hasText = Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent!.trim())
      if (!hasText) continue
      if (Number(s.fontWeight) > 600) out.push({ rule: 'weight<=600', el: label(el), value: s.fontWeight })
      if (parseFloat(s.fontSize) < 11) out.push({ rule: 'size>=11px', el: label(el), value: s.fontSize })
      if (!/^"?InterVar/.test(s.fontFamily)) out.push({ rule: 'font=InterVar', el: label(el), value: s.fontFamily })
    }
    return out
  })
}

const STEPS: [string, Record<string, unknown>][] = [
  ['0-landing', { step: 0 }],
  ['1-contact', { step: 1 }],
  ['otp', { step: 1, showOtpGate: true, contact: { email: 'contact@example.test' } }],
  ['2-facilities', { step: 2, showOtpGate: false, facilities }],
  ['3-pricing', { step: 3, selectedFacilities: facilities }],
  ['4-review', { step: 4 }],
  ['5-terms', { step: 5 }],
  ['6-commit', { step: 6 }],
  ['7-progress', { step: 7, submissionRef: 'OPT-SYN-1' }],
]

test('every opt-in step follows the brand guide', async ({ page }, info) => {
  const errors: string[] = []
  // opt-in.html's Jinja boot block is rendered by Frappe, not by this static fixture.
  page.on('pageerror', (e) => e.message !== "Unexpected token '%'" && errors.push(e.message))
  await openWizard(page)
  if (SHOTS) mkdirSync(SHOTS, { recursive: true })
  for (const [name, patch] of STEPS) {
    await setStep(page, patch)
    if (SHOTS) await page.screenshot({ path: join(SHOTS, `optin-${name}-${info.project.name}.png`), fullPage: true })
    expect(await brandViolations(page), `${name}`).toEqual([])
  }
  expect(errors).toEqual([])
})

test('landing CTA uses the brand guide red by default', async ({ page }) => {
  await openWizard(page)
  await expect(page.getByRole('button', { name: /Continue with Opt-In/ })).toHaveCSS('background-color', BRAND_RGB)
})

test('a non-hex partner colour falls back to the brand guide red', async ({ page }) => {
  await openWizard(page, 'url(https://example.test/x.png)')
  await expect(page.getByRole('button', { name: /Continue with Opt-In/ })).toHaveCSS('background-color', BRAND_RGB)
})

test('a valid partner hex colour is still honoured', async ({ page }) => {
  await openWizard(page, '#1a73e8')
  await expect(page.getByRole('button', { name: /Continue with Opt-In/ })).toHaveCSS('background-color', 'rgb(26, 115, 232)')
})
