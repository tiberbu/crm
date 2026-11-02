import { APIRequestContext, test, expect } from '@playwright/test'
import { Customer360Page, DealCustomer360 } from '../pages'
import { uniqueSuffix } from '../helpers'

/**
 * The shared e2e/.auth/csrf.json can be overwritten by another setup project
 * (quote_auth.setup.ts writes the token of ITS session), which would fail the
 * CSRF check for this suite's session. So capture the token from the session
 * this context actually carries (it is embedded in the /crm page HTML).
 */
let csrfToken: string | null = null

async function apiCsrfToken(request: APIRequestContext): Promise<string> {
	if (csrfToken) return csrfToken
	const res = await request.get('/crm')
	const html = await res.text()
	const match = html.match(/csrf_token"\] = "([^"]*)"/)
	csrfToken = match ? match[1] : ''
	return csrfToken
}

async function apiCreate(
	request: APIRequestContext,
	doctype: string,
	doc: Record<string, unknown>,
): Promise<{ name: string }> {
	const token = await apiCsrfToken(request)
	const res = await request.post(`/api/resource/${doctype}`, {
		data: doc,
		headers: { 'Content-Type': 'application/json', 'X-Frappe-CSRF-Token': token },
	})
	if (!res.ok()) throw new Error(`create ${doctype}: ${await res.text()}`)
	const body = await res.json()
	return body.data as { name: string }
}

async function apiDelete(request: APIRequestContext, doctype: string, name: string) {
	const token = await apiCsrfToken(request)
	const res = await request.delete(`/api/resource/${doctype}/${name}`, {
		headers: { 'X-Frappe-CSRF-Token': token },
	})
	if (!res.ok()) throw new Error(`delete ${doctype} ${name}: ${await res.text()}`)
}

/**
 * Customer 360 — admin 360-degree customer view (deal tab + nav page).
 *
 * The dev site carries a Won deal (50048, CORE CLINIC) whose customer came in
 * through the LIFEMED LTD partner network, with an opted-in facility, an
 * onboarding request, and a paid + an open order/invoice pair. The assertions
 * below are guarded: if that record is ever removed, the deal-scoped test is
 * skipped rather than failing.
 */

const REAL_DEAL = '50048'

async function realDealExists(request: any): Promise<boolean> {
	try {
		const res = await request.get(`/api/resource/CRM%20Deal/${REAL_DEAL}`)
		return res.ok()
	} catch {
		return false
	}
}

test.describe('Customer 360', () => {
	let seededOrg: { name: string } | null = null
	let seededDeal: { name: string } | null = null
	const suffix = uniqueSuffix()
	const orgName = `E2E 360 Org ${suffix}`

	test.beforeAll(async ({ request }) => {
		seededOrg = await apiCreate(request, 'CRM Organization', {
			organization_name: orgName,
		})
		seededDeal = await apiCreate(request, 'CRM Deal', {
			organization: orgName,
			status: 'Qualification',
			email: `e2e-360-${suffix}@example.com`,
		})
	})

	test.afterAll(async ({ request }) => {
		if (seededDeal) {
			await apiDelete(request, 'CRM Deal', seededDeal.name)
		}
		if (seededOrg) {
			await apiDelete(request, 'CRM Organization', seededOrg.name)
		}
	})

	test('shows the Customer 360 nav item and opens a seeded org 360', async ({
		page,
		request,
	}) => {
		const p360 = new Customer360Page(page)
		await p360.goto()

		// Search for the seeded organization (min 3 chars, 600ms debounce).
		await p360.search(orgName)
		await p360.openOrganization(orgName)

		// The 360 view renders the customer and the seeded deal.
		await expect(page.getByText(orgName).first()).toBeVisible({
			timeout: 15000,
		})
		await expect(p360.kpiSection).toBeVisible()
		await expect(p360.billingSection).toBeVisible()
		await expect(p360.facilitiesSection).toBeVisible()
	})

	test('opens a seeded deal from search and shows its 360', async ({ page }) => {
		const p360 = new Customer360Page(page)
		await p360.goto()

		// Searching the org surfaces its deal in the Deals result group.
		await p360.search(orgName)
		await page
			.getByRole('button', { name: new RegExp(`Open 360 for ${seededDeal?.name}`) })
			.first()
			.click()

		await expect(p360.kpiSection).toBeVisible({ timeout: 15000 })
	})

	test('short search does not query the server', async ({ page }) => {
		const p360 = new Customer360Page(page)
		await p360.goto()

		await p360.searchInput.fill('ab')
		// Under 3 characters the results panel must not appear.
		await page.waitForTimeout(1200)
		await expect(page.locator('.mx-6.mt-4')).toBeHidden()
	})

	test('deal page exposes the Customer 360 tab for managers', async ({
		page,
		request,
	}) => {
		if (!(await realDealExists(request))) {
			test.skip(true, 'Real won deal 50048 not present on this site')
			return
		}
		const deal360 = new DealCustomer360(page)
		await deal360.openDeal(REAL_DEAL)
		await deal360.open360Tab()

		// Partner attribution: the customer came in through the partner network.
		await expect(
			page.getByText('LIFEMED LTD').first(),
		).toBeVisible({ timeout: 15000 })

		// KPI tiles, provisioning and billing sections render.
		await expect(
			page.getByText('Package Paid', { exact: true }),
		).toBeVisible()
		await expect(
			page.getByText('Site Provisioning', { exact: true }),
		).toBeVisible()
		await expect(
			page.getByText('Facilities & Provisioning', { exact: true }),
		).toBeVisible()

		// The customer's facility is listed with its network membership.
		await expect(page.getByText('CORE CLINIC').first()).toBeVisible()
	})
})
