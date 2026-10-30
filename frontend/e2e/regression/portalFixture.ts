import { createServer, type Server } from 'http'
import { existsSync, readFileSync } from 'fs'
import { extname, join } from 'path'
import { fileURLToPath } from 'url'
import type { Page, Route } from '@playwright/test'

// Serves the built CX Portal and facility onboarding bundles so specs run the real UI with only Frappe's JSON API mocked.
const BUILD = fileURLToPath(
  new URL('../../../crm/public/frontend', import.meta.url),
).replace(/\/$/, '')
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

export async function startPortalServer(): Promise<{
  server: Server
  origin: string
}> {
  const server = createServer((req, res) => {
    const url = new URL(req.url || '/', 'http://local')
    let file = ''
    if (url.pathname === '/cx-portal') file = join(BUILD, 'cx-portal.html')
    else if (url.pathname === '/facility-onboarding')
      file = join(BUILD, 'facility-onboarding.html')
    else if (url.pathname.startsWith(ASSET_PREFIX))
      file = join(BUILD, url.pathname.slice(ASSET_PREFIX.length))
    if (!file || !file.startsWith(BUILD) || !existsSync(file)) {
      res.writeHead(404).end()
      return
    }
    res.writeHead(200, {
      'content-type': MIME[extname(file)] || 'application/octet-stream',
    })
    res.end(readFileSync(file))
  })
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
  return {
    server,
    origin: `http://127.0.0.1:${(server.address() as { port: number }).port}`,
  }
}

const balance = (value: number) => ({
  status: 'ok',
  balance: value,
  usage: 0,
  has_access: value > 0,
})

// Stress data: long names, both readiness states, live and missing balances, outstanding invoices.
export const stressFacilities = [
  {
    facility_name:
      'St. Elizabeth Comprehensive Maternal and Child Health Hospital Annex',
    mfl_code: '10001',
    hfr_facility_id: 'FID-00-10001-1',
    keph_level: 'Level 4 Sub-County Hospital',
    go_live: false,
    token_package: 'Growth Clinic Annual Package',
    token_quantity: 50000,
    token_balance: balance(120),
    recent_purchase: { amount: 125000, currency: 'KES', date: '2026-10-12' },
    invoice_summary: {
      has_outstanding: true,
      outstanding_amount: 125000,
      currency: 'KES',
      invoice_name: 'ACC-SINV-0001',
      count: 1,
    },
  },
  {
    facility_name: 'Mwangaza Community Dispensary',
    mfl_code: '10002',
    hfr_facility_id: 'FID-00-10002-2',
    keph_level: 'Level 2',
    go_live: true,
    token_package: 'Starter',
    token_quantity: 5000,
    token_balance: balance(48250),
    recent_purchase: null,
    invoice_summary: null,
  },
  {
    facility_name:
      'Nyandarua West Integrated Medical Centre and Diagnostic Laboratory Services',
    mfl_code: '10003',
    hfr_facility_id: '',
    keph_level: 'Level 3',
    go_live: false,
    token_package: '',
    token_quantity: 0,
    token_balance: null,
    recent_purchase: null,
    invoice_summary: null,
  },
]

export const tokenPackages = [
  {
    item_code: 'PKG-FREE',
    display_name: 'Free trial',
    token_quantity: 1000,
    price: 0,
    price_ex_vat: 0,
    gross_total: 0,
    currency: 'KES',
    vat_label: 'VAT exempt',
    description: 'Try CareVerse with a starter allocation.',
  },
  {
    item_code: 'PKG-STARTER',
    display_name: 'Starter',
    token_quantity: 5000,
    price: 10000,
    price_ex_vat: 8621,
    gross_total: 10000,
    currency: 'KES',
    vat_label: 'Incl. 16% VAT',
    description: 'For small dispensaries.\nEmail support.',
  },
  {
    item_code: 'PKG-GROWTH',
    display_name: 'Growth Clinic Annual Package',
    token_quantity: 50000,
    price: 125000,
    price_ex_vat: 107759,
    gross_total: 125000,
    currency: 'KES',
    vat_label: 'Incl. 16% VAT',
    description:
      'For busy clinics with several departments.\nPriority onboarding.\nQuarterly review.',
  },
]

export function portalContext(facilities = stressFacilities) {
  return {
    user: 'owner@example.test',
    customer_accounts: [
      {
        customer: 'Example Healthcare Holdings',
        organization:
          'Example Healthcare Holdings Limited (Nairobi Regional Operations)',
        network: 'CareVerse Partner Network',
        facilities,
        open_orders: [
          {
            name: 'SAL-ORD-0001',
            crm_token_package_item: 'PKG-STARTER',
            crm_token_facility_mfl: '10002',
            grand_total: 10000,
            currency: 'KES',
            transaction_date: '2026-10-20',
            can_create_invoice: true,
          },
        ],
        open_invoices: [
          {
            name: 'ACC-SINV-0001',
            invoice_number: 'ACC-SINV-0001',
            crm_token_facility_mfl: '10001',
            amount: 125000,
            currency: 'KES',
            posting_date: '2026-10-12',
            due_date: '2026-10-26',
          },
        ],
        payments: [
          {
            name: 'PAY-0001',
            amount: 10000,
            mode_of_payment: 'M-Pesa',
            status: 'Pending Verification',
            posting_date: '2026-10-21',
            reference_no: 'QWE123RTY',
            invoice: '',
          },
        ],
      },
    ],
    ois: [],
    token_packages: tokenPackages,
    paybill_info: { paybill: '000000', account_hint: 'Invoice number' },
  }
}

export type ApiHandler = (
  method: string,
  body: Record<string, unknown>,
  route: Route,
) => Promise<boolean | void> | boolean | void

export async function mockPortalApi(
  page: Page,
  context = portalContext(),
  extra?: ApiHandler,
) {
  await page.route('**/api/method/**', async (route) => {
    const method = route.request().url().split('/api/method/')[1].split('?')[0]
    const body =
      (route.request().postDataJSON?.() as Record<string, unknown>) || {}
    if (extra && (await extra(method, body, route))) return
    if (method === 'crm.api.website_redirect.get_portal_context')
      return route.fulfill({ json: { message: { data: context } } })
    if (method === 'crm.api.customer_experience.get_user_profile')
      return route.fulfill({
        json: {
          message: {
            data: {
              email: 'owner@example.test',
              full_name: 'Wanjiru Example-Kamau',
              national_id: '12****78',
              identification_type: 'National ID',
              mobile_no: '+254700000000',
              organization: context.customer_accounts[0]?.organization,
            },
          },
        },
      })
    if (
      method === 'crm.api.hfr.ensure_provisioning_draft' ||
      method === 'crm.api.hfr.get_provisioning_status'
    )
      return route.fulfill({
        json: {
          message: {
            message: 'Status synced.',
            configured: true,
            status: 'draft',
            progress: 20,
          },
        },
      })
    return route.fulfill({ json: { message: { data: {} } } })
  })
}

// nav: sidebar label; tab: phone bottom-bar label, or null when it sits under "More".
export const VIEWS = [
  { key: 'dashboard', nav: 'Dashboard', tab: 'Home' },
  { key: 'facilities', nav: 'Facilities', tab: 'Facilities' },
  { key: 'pricing', nav: 'Plans & Pricing', tab: null },
  { key: 'billing', nav: 'Billing', tab: 'Billing' },
  { key: 'profile', nav: 'My Profile', tab: 'Profile' },
]

export async function openView(page: Page, key: string) {
  const view = VIEWS.find((item) => item.key === key)!
  if ((page.viewportSize()?.width || 0) < 768) {
    const bar = page.getByRole('navigation', { name: 'Primary navigation' })
    if (view.tab)
      return bar.getByRole('button', { name: view.tab, exact: true }).click()
    await bar.getByRole('button', { name: 'More navigation options' }).click()
    return bar.getByRole('button', { name: view.nav }).click()
  }
  await page
    .getByRole('button', {
      name: new RegExp(`^\\s*${view.nav.split(' ')[0]}`, 'i'),
    })
    .filter({ visible: true })
    .first()
    .click()
}

type LayoutIssue = { kind: string; detail: string }

// Runs in the page: finds text boxes that intersect a different element's text box,
// and clipped controls. Ellipsis truncation is intentional and is not reported.
export async function auditLayout(page: Page): Promise<LayoutIssue[]> {
  return page.evaluate(() => {
    const issues: { kind: string; detail: string }[] = []
    const doc = document.documentElement
    if (doc.scrollWidth > window.innerWidth + 1)
      issues.push({
        kind: 'page-overflow-x',
        detail: `${doc.scrollWidth}px wide in a ${window.innerWidth}px viewport`,
      })

    const visible = (el: Element) => {
      const style = getComputedStyle(el)
      if (
        style.visibility === 'hidden' ||
        style.display === 'none' ||
        Number(style.opacity) === 0
      )
        return false
      const r = el.getBoundingClientRect()
      return r.width > 0 && r.height > 0
    }
    // Fixed or sticky chrome (headers, tab bars, summary bars) may cover content scrolled beneath it.
    const pinned = (el: Element) => {
      for (let node: Element | null = el; node; node = node.parentElement) {
        const { position } = getComputedStyle(node)
        if (position === 'fixed' || position === 'sticky') return node
      }
      return null
    }
    const label = (el: Element) =>
      (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 60)
    const boxes: { el: Element; rect: DOMRect }[] = []
    const walker = document.createTreeWalker(
      document.body,
      NodeFilter.SHOW_TEXT,
    )
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (!node.textContent?.trim()) continue
      const el = node.parentElement
      if (
        !el ||
        !visible(el) ||
        el.closest('[aria-hidden="true"], svg, script, style')
      )
        continue
      const range = document.createRange()
      range.selectNodeContents(node)
      for (const raw of Array.from(range.getClientRects())) {
        const rect = DOMRect.fromRect(raw)
        for (
          let anc: Element | null = el;
          anc && anc !== document.body;
          anc = anc.parentElement
        ) {
          const { overflowX, overflowY } = getComputedStyle(anc)
          if (overflowX === 'visible' && overflowY === 'visible') continue
          const clip = anc.getBoundingClientRect()
          const left = Math.max(rect.left, clip.left),
            right = Math.min(rect.right, clip.right)
          const top = Math.max(rect.top, clip.top),
            bottom = Math.min(rect.bottom, clip.bottom)
          rect.x = left
          rect.y = top
          rect.width = Math.max(0, right - left)
          rect.height = Math.max(0, bottom - top)
        }
        if (rect.width < 2 || rect.height < 2) continue
        boxes.push({ el, rect })
      }
    }
    const seen = new Set<string>()
    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        const a = boxes[i],
          b = boxes[j]
        if (a.el === b.el || a.el.contains(b.el) || b.el.contains(a.el))
          continue
        const dx =
          Math.min(a.rect.right, b.rect.right) -
          Math.max(a.rect.left, b.rect.left)
        const dy =
          Math.min(a.rect.bottom, b.rect.bottom) -
          Math.max(a.rect.top, b.rect.top)
        if (dx > 2 && dy > 2) {
          // Ignore content stacked under fixed chrome (header, bottom tabs) while scrolled.
          if (pinned(a.el) !== pinned(b.el)) continue
          const key = `${label(a.el)}|${label(b.el)}`
          if (seen.has(key)) continue
          seen.add(key)
          issues.push({
            kind: 'text-overlap',
            detail: `"${label(a.el)}" overlaps "${label(b.el)}"`,
          })
        }
      }
    }
    for (const el of Array.from(
      document.querySelectorAll('button, a, [role="button"], input, select'),
    )) {
      if (!visible(el)) continue
      const style = getComputedStyle(el)
      const clipped =
        el.scrollWidth > el.clientWidth + 1 &&
        style.textOverflow !== 'ellipsis' &&
        el.tagName !== 'INPUT' &&
        el.tagName !== 'SELECT'
      if (clipped && style.overflow !== 'visible')
        issues.push({
          kind: 'control-clipped',
          detail: label(el) || el.tagName,
        })
      const r = el.getBoundingClientRect()
      if (
        r.right > window.innerWidth + 1 &&
        !el.closest('[class*="overflow-x"]')
      )
        issues.push({
          kind: 'control-offscreen',
          detail: label(el) || el.tagName,
        })
    }
    return issues
  })
}

export type TypeSample = {
  text: string
  size: number
  weight: number
  ratio: number
  required: number
  opacity: number
  color: string
  chip: boolean
}

// Runs in the page: every visible text node's size, weight, inherited opacity and WCAG
// contrast against its composited background (translucent layers are blended down to an
// opaque ancestor or the page colour). `required` is 3 for large text, 4.5 otherwise.
export async function sampleTypography(page: Page): Promise<TypeSample[]> {
  return page.evaluate(() => {
    const ctx = new OffscreenCanvas(1, 1).getContext('2d', {
      willReadFrequently: true,
    })!
    const rgba = (css: string): number[] => {
      ctx.clearRect(0, 0, 1, 1)
      ctx.fillStyle = '#000'
      ctx.fillStyle = css
      ctx.fillRect(0, 0, 1, 1)
      const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data
      return [r, g, b, a / 255]
    }
    const blend = (top: number[], under: number[]) =>
      [0, 1, 2].map((i) => top[i] * top[3] + under[i] * (1 - top[3])).concat(1)
    const lum = (c: number[]) => {
      const [r, g, b] = c.slice(0, 3).map((v) => {
        const s = v / 255
        return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
      })
      return 0.2126 * r + 0.7152 * g + 0.0722 * b
    }
    const background = (el: Element) => {
      const layers: number[][] = []
      for (let node: Element | null = el; node; node = node.parentElement) {
        const c = rgba(getComputedStyle(node).backgroundColor)
        if (c[3] > 0) layers.push(c)
        if (c[3] >= 1) break
      }
      let base =
        layers.length && layers[layers.length - 1][3] >= 1
          ? layers.pop()!
          : rgba(getComputedStyle(document.body).backgroundColor || '#fff')
      if (base[3] < 1) base = blend(base, [255, 255, 255, 1])
      for (const layer of layers.reverse()) base = blend(layer, base)
      return base
    }
    const out: TypeSample[] = []
    const walker = document.createTreeWalker(
      document.body,
      NodeFilter.SHOW_TEXT,
    )
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const text = node.textContent?.trim()
      const el = node.parentElement
      if (
        !text ||
        !el ||
        el.closest('script, style, svg, [aria-hidden="true"], .sr-only')
      )
        continue
      const style = getComputedStyle(el)
      const rect = el.getBoundingClientRect()
      if (
        style.visibility === 'hidden' ||
        style.display === 'none' ||
        rect.width === 0 ||
        rect.height === 0
      )
        continue
      let opacity = 1
      for (let n: Element | null = el; n; n = n.parentElement)
        opacity *= Number(getComputedStyle(n).opacity)
      if (opacity === 0) continue
      const bg = background(el)
      const fg = blend(
        [...rgba(style.color).slice(0, 3), rgba(style.color)[3] * opacity],
        bg,
      )
      const [hi, lo] = [lum(fg), lum(bg)].sort((a, b) => b - a)
      const size = parseFloat(style.fontSize)
      const weight = Number(style.fontWeight)
      const large = size >= 24 || (size >= 18.66 && weight >= 700)
      out.push({
        text: text.slice(0, 50),
        size,
        weight,
        ratio: Math.round(((hi + 0.05) / (lo + 0.05)) * 100) / 100,
        required: large ? 3 : 4.5,
        opacity: Math.round(opacity * 100) / 100,
        color: style.color,
        chip: Boolean(el.closest('.rounded-full, [class~="py-0.5"]')),
      })
    }
    return out
  })
}
