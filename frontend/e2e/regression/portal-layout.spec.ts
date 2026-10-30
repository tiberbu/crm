import { mkdirSync } from 'fs'
import { join } from 'path'
import { expect, test } from '@playwright/test'
import type { Server } from 'http'
import {
  auditLayout,
  mockPortalApi,
  openView,
  startPortalServer,
  stressFacilities,
  VIEWS,
} from './portalFixture'

// Layout audit of every CX Portal view with long names and every status, at phone,
// tablet and desktop widths: no sideways page scroll, no text drawn over other text,
// and no control clipped off its container. SCREENSHOT_DIR also saves full-page captures.
const SHOTS = process.env.SCREENSHOT_DIR || ''

let server: Server
let origin = ''
test.beforeAll(async () => ({ server, origin } = await startPortalServer()))
test.afterAll(() => server.close())

for (const view of VIEWS) {
  test(`${view.key} has no overflow or overlapping text`, async ({
    page,
  }, info) => {
    await mockPortalApi(page)
    await page.goto(`${origin}/cx-portal`)
    await expect(
      page.getByText(stressFacilities[1].facility_name).first(),
    ).toBeAttached()
    await openView(page, view.key)
    await page.waitForTimeout(300)
    if (SHOTS) {
      mkdirSync(SHOTS, { recursive: true })
      await page.screenshot({
        path: join(SHOTS, `${info.project.name}-${view.key}.png`),
        fullPage: true,
      })
    }
    const issues = await auditLayout(page)
    expect(issues, JSON.stringify(issues, null, 1)).toEqual([])
  })
}

test('facility detail has no overflow or overlapping text', async ({
  page,
}, info) => {
  await mockPortalApi(page)
  await page.goto(`${origin}/cx-portal`)
  await openView(page, 'facilities')
  await page
    .getByRole('button', { name: stressFacilities[0].facility_name })
    .first()
    .click()
  await page.waitForTimeout(500)
  if (SHOTS)
    await page.screenshot({
      path: join(SHOTS, `${info.project.name}-facility-detail.png`),
      fullPage: true,
    })
  const issues = await auditLayout(page)
  expect(issues, JSON.stringify(issues, null, 1)).toEqual([])
})
