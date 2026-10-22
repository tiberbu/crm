import { createServer, type Server } from 'http'
import { existsSync, readFileSync } from 'fs'
import { extname, join } from 'path'
import { fileURLToPath } from 'url'
import { expect, test, type Page, type Route } from '@playwright/test'

const BUILD = fileURLToPath(new URL('../../../crm/public/frontend', import.meta.url)).replace(/\/$/, '')
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

let server: Server
let origin = ''

test.beforeAll(async () => {
  server = createServer((req, res) => {
    const url = new URL(req.url || '/', 'http://local')
    let file = ''
    if (url.pathname === '/cx-portal') file = join(BUILD, 'cx-portal.html')
    else if (url.pathname.startsWith(ASSET_PREFIX)) file = join(BUILD, url.pathname.slice(ASSET_PREFIX.length))
    if (!file || !file.startsWith(BUILD) || !existsSync(file)) {
      res.writeHead(404).end()
      return
    }
    res.writeHead(200, { 'content-type': MIME[extname(file)] || 'application/octet-stream' })
    res.end(readFileSync(file))
  })
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
  origin = `http://127.0.0.1:${(server.address() as { port: number }).port}`
})

test.afterAll(() => server.close())

const facility = {
  facility_name: 'FID Regression Health Centre',
  mfl_code: '88776',
  facility_fid: 'FID-29-88776-5',
  keph_level: 'Level 3',
  hfr_sync_status: '',
  membership_status: 'Active',
}

async function openFacility(
  page: Page,
  statusHandler: (route: Route) => Promise<void>,
  selectedFacility = facility,
) {
  const statusCalls: Array<{ method: string; mfl_code?: string }> = []
  await page.route('**/api/method/**', async (route) => {
    const method = route.request().url().split('/api/method/')[1].split('?')[0]
    const body = route.request().postDataJSON?.() || {}
    if (method === 'crm.api.website_redirect.get_portal_context')
      return route.fulfill({
        json: {
          message: {
            data: {
              user: 'operator@example.test',
              customer_accounts: [
                {
                  customer: 'Regression Customer',
                  organization: 'Regression Organization',
                  network: 'CareVerse Partner Network',
                  facilities: [selectedFacility],
                },
              ],
              ois: [],
              token_packages: [],
            },
          },
        },
      })
    if (method === 'crm.api.customer_experience.get_user_profile')
      return route.fulfill({ json: { message: { data: { email: 'operator@example.test' } } } })
    if (method === 'crm.api.hfr.ensure_provisioning_draft') {
      statusCalls.push({ method, mfl_code: body.mfl_code })
      return statusHandler(route)
    }
    return route.fulfill({ json: { message: { data: {} } } })
  })

  await page.goto(`${origin}/cx-portal`)
  await page.getByRole('button', { name: /Facilities/ }).first().click()
  await page.getByRole('button', { name: selectedFacility.facility_name }).click()
  return statusCalls
}

test('shows the saved HFR FID and offers a retry when status lookup temporarily fails', async ({ page }) => {
  let attempts = 0
  const statusCalls = await openFacility(page, async (route) => {
    attempts += 1
    if (attempts === 1)
      return route.fulfill({
        status: 503,
        json: { exc_type: 'Unavailable', message: 'Provisioning service temporarily unavailable.' },
      })
    return route.fulfill({ json: { message: { data: { configured: true, status: 'deployed', progress: 100 } } } })
  })

  await expect(page.getByText('FID-29-88776-5', { exact: true })).toBeVisible()
  await expect(page.getByText('A verified HFR FID is required for deployment status and setup.')).toHaveCount(0)
  await expect(page.getByRole('alert')).toContainText('temporarily unavailable')
  await expect(page.getByRole('button', { name: 'Retry check' })).toBeVisible()
  expect(statusCalls[0]).toEqual({ method: 'crm.api.hfr.ensure_provisioning_draft', mfl_code: '88776' })

  await page.getByRole('button', { name: 'Retry check' }).click()
  await expect(page.getByText('Live', { exact: true })).toBeVisible()
  await expect(page.getByText('FID-29-88776-5', { exact: true })).toBeVisible()
  expect(statusCalls).toHaveLength(2)
  expect(statusCalls[1].mfl_code).toBe('88776')
})

test('a status service mismatch names the FID the portal actually sent for resolution', async ({ page }) => {
  const statusCalls = await openFacility(page, async (route) =>
    route.fulfill({
      json: {
        message: {
          data: {
            configured: false,
            status: 'not_linked',
            message: 'An HFR Facility ID is required to look up HMIS implementation status.',
          },
        },
      },
    }),
  )

  await expect(page.getByText('FID-29-88776-5', { exact: true })).toBeVisible()
  await expect(page.getByText('FID lookup needs attention', { exact: true })).toBeVisible()
  await expect(page.getByText(/portal has HFR FID FID-29-88776-5/)).toBeVisible()
  await expect(page.getByText('A verified HFR FID is required for deployment status and setup.')).toHaveCount(0)
  expect(statusCalls[0].mfl_code).toBe('88776')
})

test('shows the resolved FID, HTTP status, and correlation ID in deployment diagnostics', async ({ page }) => {
  const unlinkedFacility = { ...facility, facility_fid: '' }
  await openFacility(page, async (route) =>
    route.fulfill({
      json: {
        message: {
          data: {
            configured: true,
            fid: 'FID-29-88776-5',
            status: 'unavailable',
            error_title: 'The deployment service could not return status',
            message: 'The status request failed.',
            correlation_id: 'crm-ta-req-123',
            error_details: '{\n  "http_status": 500,\n  "response": {\n    "response_text": "Internal Server Error"\n  }\n}',
          },
        },
      },
    }),
    unlinkedFacility,
  )

  await page.getByRole('button', { name: 'View deployment diagnostics' }).click()
  const dialog = page.getByRole('dialog', { name: 'Deployment service diagnostics' })
  await expect(dialog).toBeVisible()
  await expect(dialog).toContainText('HTTP 500')
  await expect(dialog).toContainText('Internal Server Error')
  await expect(dialog).toContainText('Correlation ID: crm-ta-req-123')
  await expect(dialog).toContainText('FID-29-88776-5')
  await dialog.getByRole('button', { name: 'Close' }).click()
  await expect(dialog).toHaveCount(0)
})
