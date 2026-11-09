import { expect, test, type Page } from '@playwright/test'
import type { Server } from 'http'
import {
  mockPortalApi,
  openView,
  portalContext,
  startPortalServer,
  stressFacilities,
} from './portalFixture'

// Low-token email alerts in the CX Portal: an owner turns the alert on for a facility,
// sets a threshold, sees the outcome of the immediate check, and the dashboard card
// shows the alert. Frappe's API is mocked; the backend contract is covered by
// crm/tests/test_token_alerts.py.
let server: Server
let origin = ''
test.beforeAll(async () => ({ server, origin } = await startPortalServer()))
test.afterAll(() => server.close())

const lowBalance = stressFacilities[0] // live balance 120
const noFid = stressFacilities[2]

async function openPortal(page: Page) {
  const saves: Record<string, unknown>[] = []
  const alerts: Record<string, Record<string, unknown>> = {}
  await mockPortalApi(page, portalContext(), async (method, body, route) => {
    if (method === 'crm.api.token_alerts.get_token_alerts') {
      await route.fulfill({ json: { message: { alerts } } })
      return true
    }
    if (method === 'crm.api.token_alerts.save_token_alert') {
      saves.push(body)
      const alert = {
        name: 'ALERT-1',
        mfl_code: body.mfl_code,
        enabled: body.enabled,
        threshold: body.threshold,
        below_threshold: 0,
      }
      alerts[String(body.mfl_code)] = alert
      const balance = lowBalance.token_balance!.balance
      await route.fulfill({
        json: {
          message: {
            alert,
            balance_status: 'ok',
            balance,
            alert_sent:
              Boolean(body.enabled) && balance <= Number(body.threshold),
          },
        },
      })
      return true
    }
  })
  await page.goto(`${origin}/cx-portal`)
  return saves
}

async function openFacility(page: Page, name: string) {
  await openView(page, 'facilities')
  await page.getByRole('button', { name }).first().click()
  await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible()
}

test('owner turns on an alert, is told the email went out, and the dashboard shows it', async ({
  page,
}) => {
  const saves = await openPortal(page)
  await openFacility(page, lowBalance.facility_name)

  const card = page.getByTestId('token-alert-card')
  await expect(card).toContainText('Available now: 120 tokens')
  await expect(card.getByTestId('token-alert-save')).toBeDisabled()

  await card.getByRole('switch').check({ force: true })
  await card.getByLabel('Email me when tokens reach').fill('500')
  await card.getByTestId('token-alert-save').click()

  await expect(card.getByTestId('token-alert-status')).toHaveText(
    /already at or below 500 tokens, so we have emailed you now/,
  )
  expect(saves).toEqual([
    { mfl_code: lowBalance.mfl_code, enabled: 1, threshold: 500 },
  ])
  await expect(card.getByTestId('token-alert-save')).toBeDisabled()

  await openView(page, 'dashboard')
  await expect(
    page.getByTestId(`facility-alert-${lowBalance.mfl_code}`),
  ).toContainText('at 500 tokens')
})

test('owner turns an alert off again', async ({ page }) => {
  const saves = await openPortal(page)
  await openFacility(page, lowBalance.facility_name)
  const card = page.getByTestId('token-alert-card')
  await card.getByRole('switch').check({ force: true })
  await card.getByLabel('Email me when tokens reach').fill('50')
  await card.getByTestId('token-alert-save').click()
  await expect(card.getByTestId('token-alert-status')).toHaveText(
    /We will email you when tokens drop to 50 tokens or below/,
  )

  await card.getByRole('switch').uncheck({ force: true })
  await card.getByTestId('token-alert-save').click()
  await expect(card.getByTestId('token-alert-status')).toHaveText(
    /Alert turned off/,
  )
  expect(saves.at(-1)).toMatchObject({ enabled: 0 })
})

test('an invalid threshold cannot be saved', async ({ page }) => {
  await openPortal(page)
  await openFacility(page, lowBalance.facility_name)
  const card = page.getByTestId('token-alert-card')
  await card.getByRole('switch').check({ force: true })
  await card.getByLabel('Email me when tokens reach').fill('0')
  await expect(card).toContainText('Enter a whole number of 1 or more.')
  await expect(card.getByTestId('token-alert-save')).toBeDisabled()
})

test('a facility without an HFR Facility ID explains why alerts are unavailable', async ({
  page,
}) => {
  await openPortal(page)
  await openFacility(page, noFid.facility_name)
  const card = page.getByTestId('token-alert-card')
  await expect(card.getByRole('switch')).toBeDisabled()
  await expect(card).toContainText('Alerts need the facility')
  await expect(page.getByTestId('facility-available-tokens-value')).toHaveText(
    'Not reported',
  )
})
