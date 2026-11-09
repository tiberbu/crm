import { readdirSync, readFileSync } from 'fs'
import { extname, join } from 'path'
import { fileURLToPath } from 'url'
import { expect, test } from '@playwright/test'

// Favicons, PWA icons and iOS splash screens must carry the Tiberbu mark in the brand
// guide red #bc1823 (docs/tiberbu-crm-centralized-theme-spec.md), never the upstream
// Frappe CRM magenta, the Frappe "F" or another hue.
const APP = fileURLToPath(new URL('../../../', import.meta.url))
const BRAND: [number, number, number] = [188, 24, 35]
const MIME: Record<string, string> = { '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml' }

const assets = [
  'crm/public/images/logo.png',
  'crm/public/images/logo.svg',
  'crm/public/images/tiberbu-mark.svg',
  'crm/public/finance-cockpit/favicon.svg',
  'frontend/public/favicon.png',
  ...readdirSync(join(APP, 'crm/public/manifest')).map((f) => `crm/public/manifest/${f}`),
]

test.describe.configure({ mode: 'parallel' })

for (const rel of assets) {
  test(`${rel} uses the brand red`, async ({ page }, info) => {
    test.skip(info.project.name !== 'laptop', 'asset check runs once')
    const data = readFileSync(join(APP, rel)).toString('base64')
    const uri = `data:${MIME[extname(rel)]};base64,${data}`
    // Dominant saturated colour of the image, sampled on a canvas.
    const top = await page.evaluate(async (src) => {
      const img = new Image()
      img.src = src
      await img.decode()
      const w = Math.min(img.naturalWidth || 300, 400)
      const h = Math.round(w * ((img.naturalHeight || 300) / (img.naturalWidth || 300)))
      const c = document.createElement('canvas')
      c.width = w
      c.height = h
      const ctx = c.getContext('2d')!
      ctx.drawImage(img, 0, 0, w, h)
      const px = ctx.getImageData(0, 0, w, h).data
      const counts = new Map<string, number>()
      for (let i = 0; i < px.length; i += 4) {
        const [r, g, b, a] = [px[i], px[i + 1], px[i + 2], px[i + 3]]
        if (a < 200 || Math.max(r, g, b) - Math.min(r, g, b) < 40) continue
        const k = [r, g, b].map((v) => Math.round(v / 6) * 6).join(',')
        counts.set(k, (counts.get(k) || 0) + 1)
      }
      return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || 'none'
    }, uri)
    const [r, g, b] = top.split(',').map(Number)
    const near = Math.abs(r - BRAND[0]) <= 8 && Math.abs(g - BRAND[1]) <= 8 && Math.abs(b - BRAND[2]) <= 8
    expect(near, `dominant colour ${top}`).toBe(true)
  })
}
