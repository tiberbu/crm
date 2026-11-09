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
	let seededCustomer: { name: string } | null = null
	let seededFacility: { name: string } | null = null
	const suffix = uniqueSuffix()
	const orgName = `E2E 360 Org ${suffix}`
	const customerName = `E2E 360 Customer ${suffix}`
	const facilityName = `E2E 360 Facility ${suffix}`

	test.beforeAll(async ({ request }) => {
		seededOrg = await apiCreate(request, 'CRM Organization', {
			organization_name: orgName,
		})
		// A billing party forces get_customer_360 to run the real Sales Invoice /
		// Payment Entry queries (a customer-less org skips them entirely).
		// The site's default customer group may be a group node, which ERPNext rejects.
		const groups = await request.get(
			'/api/resource/Customer Group?filters=' +
				encodeURIComponent(JSON.stringify([['is_group', '=', 0]])) +
				'&limit_page_length=1',
		)
		const customerGroup = (await groups.json()).data?.[0]?.name
		seededCustomer = await apiCreate(request, 'Customer', {
			customer_name: customerName,
			...(customerGroup ? { customer_group: customerGroup } : {}),
		})
		seededDeal = await apiCreate(request, 'CRM Deal', {
			organization: orgName,
			status: 'Qualification',
			email: `e2e-360-${suffix}@example.com`,
			cx_customer: seededCustomer.name,
		})
		seededFacility = await apiCreate(request, 'CRM Pre-Qualified Facility', {
			facility_name: facilityName,
			mfl_code: `9${suffix.replace(/\D/g, '').slice(0, 3)}12`,
			keph_level: 'Level 3',
			organization: orgName,
		})
	})

	test.afterAll(async ({ request }) => {
		if (seededDeal) {
			await apiDelete(request, 'CRM Deal', seededDeal.name)
		}
		if (seededFacility) {
			await apiDelete(request, 'CRM Pre-Qualified Facility', seededFacility.name)
		}
		// Best effort: the dev site's role setup can deny Customer delete even to
		// the QA user, and that restriction is not something the suite may change.
		// A leftover synthetic Customer is harmless.
		if (seededCustomer) {
			try {
				await apiDelete(request, 'Customer', seededCustomer.name)
			} catch (e) {
				console.warn(
					`leftover Customer kept (delete denied on this site): ${seededCustomer.name}`,
				)
			}
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

	test('facility search hits open the facility, with its owner one toggle away', async ({ page }) => {
		const p360 = new Customer360Page(page)
		await p360.goto()

		// The seeded facility is surfaced in the Facilities result group.
		await p360.search(facilityName)
		await p360.openFacility(facilityName)

		// Clicking it opens the facility's own scope; the owner is named in the scope bar.
		await expect(p360.kpiSection).toBeVisible({ timeout: 15000 })
		await expect(p360.scopeBar).toContainText(facilityName)
		await expect(p360.scopeBar).toContainText(orgName)
		await expect(p360.scopeOption('This facility')).toBeChecked()
		await expect(page).toHaveURL(/scope=facility/)

		// "All facilities" widens to the parent organization's 360 view.
		await p360.scopeOption('All facilities').click()
		await expect(page).toHaveURL(/scope=organization/)
		await expect(page.getByText(orgName).first()).toBeVisible()
	})

	test('short search does not query the server', async ({ page }) => {
		const p360 = new Customer360Page(page)
		await p360.goto()

		await p360.searchInput.fill('ab')
		// Under 3 characters the results panel must not appear.
		await page.waitForTimeout(1200)
		await expect(p360.results).toBeHidden()
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

		// Detail rows deep-link into the Finance Cockpit record views.
		const invoiceLink = page
			.locator('a[href*="finance-cockpit#/invoices?doctype=Sales"]')
			.first()
		await expect(invoiceLink).toBeVisible()
		await expect(
			page.locator('a[href*="finance-cockpit#/orders?doctype=Sales"]').first(),
		).toBeVisible()
		await expect(
			page.locator(
				'a[href*="finance-cockpit#/quotes?doctype=CRM+Pre-Qualified"]',
			).first(),
		).toBeVisible()

		// Clicking the invoice row opens its record in the Finance Cockpit.
		const href = (await invoiceLink.getAttribute('href')) as string
		const invoiceName = new URLSearchParams(href.split('?')[1]).get('name')
		expect(invoiceName).toBeTruthy()
		const [popup] = await Promise.all([
			page.waitForEvent('popup'),
			invoiceLink.click(),
		])
		await popup.waitForLoadState('domcontentloaded')
		await expect(
			popup.getByText(invoiceName as string, { exact: true }).first(),
		).toBeVisible({ timeout: 20000 })
		await popup.close()
	})
})
