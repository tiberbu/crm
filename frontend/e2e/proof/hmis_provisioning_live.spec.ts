import { mkdirSync } from 'fs'
import { expect, test, type Page } from '@playwright/test'

// Opens every facility in a real portal account and checks that the HMIS
// implementation section shows what the live CRM + setup service report.
// Run: LIVE_BASE_URL=<site base URL> LIVE_SID=<portal session> \
//   npx playwright test -c e2e/proof/hmis_live.config.ts

const BASE = process.env.LIVE_BASE_URL || ''
const SID = process.env.LIVE_SID || ''
const OUT = process.env.PROOF_OUT || '/tmp/hmis-live-proof'
const LABELS: Record<string, string> = {
  preparing: 'Preparing setup',
  queued: 'Request received',
  deploying: 'Deploying',
  configuring: 'Configuring',
  live: 'Live',
  blocked: 'Setup needs information',
  needs_attention: 'Needs attention',
}

test.skip(
  !BASE || !SID,
  'Set LIVE_BASE_URL and LIVE_SID to run the live proof.',
)

type Facility = { facility_name: string; mfl_code: string }

async function signIn(page: Page) {
  const { hostname } = new URL(BASE)
  await page
    .context()
    .addCookies([
      {
        name: 'sid',
        value: SID,
        domain: hostname,
        path: '/',
        secure: true,
        httpOnly: true,
      },
    ])
}

async function facilities(page: Page): Promise<Facility[]> {
  const res = await page.request.get(
    `${BASE}/api/method/crm.api.website_redirect.get_portal_context`,
  )
  expect(res.ok()).toBeTruthy()
  const body = await res.json()
  const data = body.message?.data || body.message
  return (data.customer_accounts || []).flatMap(
    (account: { facilities?: Facility[] }) => account.facilities || [],
  )
}

test('each facility shows its live HMIS setup state, polling only by read', async ({
  page,
}) => {
  mkdirSync(OUT, { recursive: true })
  await signIn(page)
  const rows = await facilities(page)
  expect(rows.length).toBeGreaterThan(0)
  await page.clock.install()

  for (const facility of rows) {
    const ensure = page.waitForResponse(
      (r) => r.url().includes('crm.api.hfr.ensure_provisioning_draft'),
      { timeout: 120000 },
    )
    await page.goto(`${BASE}/cx-portal`)
    await page
      .getByRole('button', { name: /Facilities/ })
      .first()
      .click()
    // Scope to the facility's table row: a facility can share its name with the account menu.
    await page
      .getByRole('row')
      .filter({ hasText: facility.mfl_code })
      .getByRole('button', { name: facility.facility_name, exact: true })
      .click()
    const response = await ensure
    expect(response.status(), facility.mfl_code).toBe(200)
    const status = (await response.json()).message
    const phase = status.journey?.phase
    console.log(
      `${facility.mfl_code}: TA status=${status.status} phase=${phase} submission=${status.submission?.state || '-'} estimate=${status.journey?.estimate?.label || '-'}`,
    )

    // The original bug: the portal showed this fallback for every facility.
    await expect(
      page.getByText('Implementation status has not been checked.'),
    ).toHaveCount(0)
    expect(
      status.journey,
      'every status response carries a journey',
    ).toBeTruthy()
    const label = status.journey.label || LABELS[phase]
    if (label)
      await expect(page.getByText(label, { exact: true }).first()).toBeVisible()
    if (status.journey.detail)
      await expect(page.getByText(status.journey.detail).first()).toBeVisible()

    if (phase === 'live') {
      const card = page.getByTestId('hmis-live-site')
      await expect(card).toBeVisible()
      await expect(card).toContainText('How to sign in')
      if (status.journey.site?.url)
        await expect(
          card.getByRole('link', { name: /Open HMIS/ }),
        ).toHaveAttribute(
          'href',
          status.journey.site.login_url || status.journey.site.url,
        )
    }
    if (status.journey.poll) {
      await expect(page.getByTestId('hmis-setup-journey')).toBeVisible()
      if (status.journey.estimate)
        await expect(page.getByTestId('hmis-setup-estimate')).toHaveText(
          status.journey.estimate.label,
        )
      await expect(page.getByTestId('hmis-auto-refresh')).toHaveText(
        /every 5 minutes/,
      )
      // Advance the page clock 5 minutes: the portal must re-read with GET, not re-send ensure.
      const poll = page.waitForResponse(
        (r) => r.url().includes('crm.api.hfr.get_provisioning_status'),
        { timeout: 120000 },
      )
      await page.clock.fastForward('05:05')
      const polled = await poll
      expect(polled.request().method()).toBe('GET')
      expect(polled.status()).toBe(200)
      const polledStatus = (await polled.json()).message
      expect(polledStatus.journey?.phase).toBeTruthy()
      console.log(
        `${facility.mfl_code}: poll GET 200 phase=${polledStatus.journey.phase}`,
      )
    }
    await page
      .locator('section')
      .filter({ hasText: 'HMIS implementation' })
      .first()
      .screenshot({ path: `${OUT}/${facility.mfl_code}.png` })
  }
})
