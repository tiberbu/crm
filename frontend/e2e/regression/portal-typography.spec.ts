import { expect, test, type Page } from '@playwright/test'
import type { Server } from 'http'
import {
  mockPortalApi,
  openView,
  sampleTypography,
  startPortalServer,
  stressFacilities,
  VIEWS,
} from './portalFixture'

// Readability gate for the CX Portal (docs/cx-portal-token-alerts-and-ui-review.md, round 2):
// WCAG AA contrast against the composited background, nothing under 11px, running text
// (four or more words, outside chips) at 12px or more, and only the regular, medium and semibold weights.
let server: Server
let origin = ''
test.beforeAll(async () => ({ server, origin } = await startPortalServer()))
test.afterAll(() => server.close())

const WEIGHTS = new Set([400, 420, 500, 600])

async function expectReadable(page: Page, view: string) {
  const samples = await sampleTypography(page)
  const describe = (s: (typeof samples)[number]) =>
    `${s.size}px w${s.weight} ${s.ratio}:1 "${s.text}"`
  const lowContrast = samples.filter((s) => s.ratio < s.required).map(describe)
  const tiny = samples.filter((s) => s.size < 11).map(describe)
  // Chips and pills may be 11px; running text may not.
  const smallProse = samples
    .filter((s) => s.size < 12 && !s.chip && s.text.split(/\s+/).length >= 4)
    .map(describe)
  const heavy = samples.filter((s) => !WEIGHTS.has(s.weight)).map(describe)
  expect({ view, lowContrast, tiny, smallProse, heavy }).toEqual({
    view,
    lowContrast: [],
    tiny: [],
    smallProse: [],
    heavy: [],
  })
}

async function openPortal(page: Page) {
  await mockPortalApi(page)
  await page.goto(`${origin}/cx-portal`)
  await expect(
    page.getByText(stressFacilities[1].facility_name).first(),
  ).toBeAttached()
}

for (const view of VIEWS) {
  test(`${view.key} text is readable`, async ({ page }) => {
    await openPortal(page)
    await openView(page, view.key)
    await page.waitForTimeout(300)
    await expectReadable(page, view.key)
  })
}

test('facility page text is readable', async ({ page }) => {
  await openPortal(page)
  await openView(page, 'facilities')
  await page
    .getByRole('button', { name: stressFacilities[0].facility_name })
    .first()
    .click()
  await expect(
    page.getByRole('heading', {
      level: 1,
      name: stressFacilities[0].facility_name,
    }),
  ).toBeVisible()
  await expectReadable(page, 'facility-detail')
})
