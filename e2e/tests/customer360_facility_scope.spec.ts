import { readFileSync } from 'fs'
import { expect, Page, test } from '@playwright/test'
import { Customer360Page } from '../pages'

/**
 * Customer 360 — clearable search, closable results, facility scope and tabs (2026-11-09).
 * Spec: _bmad-output/customer-360-facility-scope/planning-artifacts/customer-360-facility-scope-spec.md
 *
 * Needs the synthetic fixture crm.tests.e2e_customer360_fixture.setup for this run; pass its JSON
 * output file as E2E_C360_FIXTURE and sign in as its admin (FRAPPE_USER / FRAPPE_PASSWORD).
 * Optional: SCREENSHOT_DIR to keep the per-viewport screenshots.
 */

type Fixture = Record<string, string>
const fixturePath = process.env.E2E_C360_FIXTURE
const fx: Fixture = fixturePath ? JSON.parse(readFileSync(fixturePath, 'utf8')) : {}

const VIEWPORTS = [
	{ name: 'phone', width: 390, height: 844 },
	{ name: 'tablet', width: 768, height: 1024 },
	{ name: 'laptop', width: 1280, height: 800 },
	{ name: 'desktop', width: 1536, height: 900 },
]

async function shot(page: Page, name: string) {
	const dir = process.env.SCREENSHOT_DIR
	await test.info().attach(name, { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' })
	if (dir) await page.screenshot({ path: `${dir}/${name}.png`, fullPage: true })
}

/** Brand guide: InterVar only, weights 400–600, sentence case (no uppercase transforms). */
async function brandViolations(page: Page, selector: string) {
	return page.evaluate((sel) => {
		const issues: string[] = []
		for (const root of Array.from(document.querySelectorAll(sel))) {
			for (const el of [root, ...Array.from(root.querySelectorAll('*'))] as HTMLElement[]) {
				if (!el.textContent?.trim() || el.offsetParent === null) continue
				const style = getComputedStyle(el)
				if (Number(style.fontWeight) > 600) issues.push(`weight ${style.fontWeight}: ${el.textContent.trim().slice(0, 40)}`)
				if (style.textTransform === 'uppercase') issues.push(`uppercase: ${el.textContent.trim().slice(0, 40)}`)
				if (!/inter/i.test(style.fontFamily)) issues.push(`font ${style.fontFamily}: ${el.textContent.trim().slice(0, 40)}`)
			}
		}
		return [...new Set(issues)]
	}, selector)
}

test.describe('Customer 360 facility scope', () => {
	test.skip(!fixturePath, 'Set E2E_C360_FIXTURE to the e2e_customer360_fixture output')

	test('the search can be cleared and its results closed', async ({ page }) => {
		const p360 = new Customer360Page(page)
		await p360.goto()

		await p360.search(`C360 Clinic A ${fx.run}`)
		await expect(p360.results.getByTestId('c360-facility-result')).toHaveCount(1)
		await shot(page, 'c360-1-results-open')

		// Close button.
		await p360.closeResultsButton.click()
		await expect(p360.results).toBeHidden()
		// Focusing the box reopens the same results; Esc closes them.
		await p360.searchInput.click()
		await expect(p360.results).toBeVisible()
		await p360.searchInput.press('Escape')
		await expect(p360.results).toBeHidden()
		// A click outside closes them.
		await p360.searchInput.click()
		await expect(p360.results).toBeVisible()
		await page.getByRole('heading', { name: 'Customer 360' }).click()
		await expect(p360.results).toBeHidden()

		// The clear button empties the box and closes the results.
		await expect(p360.clearButton).toBeVisible()
		await p360.clearButton.click()
		await expect(p360.searchInput).toHaveValue('')
		await expect(p360.results).toBeHidden()
		await expect(p360.clearButton).toBeHidden()
	})

	test('a facility opens in its own scope and widens to its owner', async ({ page }) => {
		const p360 = new Customer360Page(page)
		await p360.goto()

		// Search matches the Facility ID, and the result shows it beside the MFL code.
		await p360.search(fx.a_fid)
		const hit = p360.results.getByTestId('c360-facility-result').first()
		await expect(hit).toContainText(fx.a_name)
		await expect(hit).toContainText(`Facility ID: ${fx.a_fid}`)
		await expect(hit).toContainText(`MFL: ${fx.a_mfl}`)
		await hit.click()

		// Facility scope by default, carried in the URL; the view opens on the Overview tab.
		await expect(page).toHaveURL(new RegExp(`facility=${fx.a_facility}`))
		await expect(page).toHaveURL(/scope=facility/)
		await expect(p360.results).toBeHidden()
		await expect(p360.scopeBar).toContainText(fx.a_name)
		await expect(p360.scopeBar).toContainText(fx.a_fid)
		await expect(p360.scopeBar).toContainText(fx.organization)
		await expect(p360.scopeOption('This facility')).toBeChecked()
		await expect(p360.tab('Overview')).toHaveAttribute('aria-selected', 'true')
		await expect(page.getByTestId('c360-attention')).toContainText('Open orders · 1')

		// Tab labels carry facility A's counts: 1 order, its quotes, 0 invoices, 1 facility.
		const aQuotes = Number(fx.a_quote_count)
		await expect(p360.tab('Orders')).toHaveText(/Orders\s*1$/)
		await expect(p360.tab('Quotes')).toHaveText(new RegExp(`Quotes\\s*${aQuotes}$`))
		await expect(p360.tab('Billing')).toHaveText(/Billing\s*0$/)
		await expect(p360.tab('Facilities')).toHaveText(/Facilities\s*1$/)
		await expect(page.getByTestId('c360-unattributed-note')).toContainText("1 record isn't tied to one facility.")
		expect(await brandViolations(page, '[data-testid="c360-scope-bar"], [data-testid="c360-unattributed-note"], [data-testid="c360-tabs"]')).toEqual([])
		await shot(page, 'c360-2-facility-overview')

		// Only one tab's list is on the page at a time.
		await p360.openTab('Orders')
		await expect(page).toHaveURL(/tab=orders/)
		await expect(p360.rows('order')).toHaveCount(1)
		await expect(p360.rows('order').first()).toContainText(fx.a_order)
		await expect(p360.rows('quote')).toHaveCount(0)
		// The facility view needs no Facility column.
		await expect(page.getByTestId('c360-orders').getByRole('columnheader', { name: 'Facility' })).toHaveCount(0)

		// Quotes page at 10 rows.
		await p360.openTab('Quotes')
		await expect(p360.rows('quote')).toHaveCount(10)
		expect(aQuotes).toBeGreaterThan(10)
		await expect(p360.pagerLabel).toHaveText(`1–10 of ${aQuotes}`)
		await page.getByTestId('c360-pager-next').click()
		await expect(p360.rows('quote')).toHaveCount(aQuotes - 10)
		await expect(p360.pagerLabel).toHaveText(`11–${aQuotes} of ${aQuotes}`)
		await expect(page.getByTestId('c360-pager-next')).toBeDisabled()
		await expect(page.getByTestId('c360-quotes').getByText(fx.account_quote)).toHaveCount(0)
		await shot(page, 'c360-3-facility-quotes-page-2')

		await p360.openTab('Billing')
		await expect(p360.rows('invoice')).toHaveCount(0)
		await expect(page.getByTestId('c360-billing')).toContainText('No invoices yet')
		await p360.openTab('Facilities')
		await expect(p360.rows('facility')).toHaveCount(1)
		await expect(p360.rows('facility').first()).toContainText(`Facility ID: ${fx.a_fid}`)

		// All facilities keeps the open tab and shows the owner's full picture.
		await p360.openTab('Billing')
		await p360.scopeOption('All facilities').click()
		await expect(page).toHaveURL(/scope=organization/)
		await expect(page).toHaveURL(/tab=billing/)
		await expect(p360.tab('Billing')).toHaveAttribute('aria-selected', 'true')
		await expect(p360.rows('invoice')).toHaveCount(1)
		await expect(p360.rows('invoice').first()).toContainText(fx.b_invoice)
		await expect(p360.rows('invoice').first()).toContainText(fx.b_name)
		await expect(p360.tab('Orders')).toHaveText(/Orders\s*2$/)
		await expect(p360.tab('Quotes')).toHaveText(new RegExp(`Quotes\\s*${fx.quote_count}$`))
		await expect(p360.tab('Facilities')).toHaveText(/Facilities\s*2$/)
		await expect(page.getByTestId('c360-unattributed-note')).toBeHidden()
		await shot(page, 'c360-4-all-facilities-billing')
		await p360.openTab('Orders')
		await expect(p360.rows('order')).toHaveCount(2)
		await expect(page.getByTestId('c360-orders').getByRole('columnheader', { name: 'Facility' })).toBeVisible()

		// Scope and tab survive a reload and the back button.
		await page.reload()
		await p360.dismissGettingStarted()
		await expect(p360.scopeOption('All facilities')).toBeChecked()
		await expect(p360.tab('Orders')).toHaveAttribute('aria-selected', 'true')
		await p360.scopeOption('This facility').click()
		await expect(p360.rows('order')).toHaveCount(1)
		await page.getByTestId('c360-unattributed-note').getByRole('button', { name: 'Show all facilities' }).click()
		await expect(p360.scopeOption('All facilities')).toBeChecked()
		await expect(p360.rows('order')).toHaveCount(2)

		// A KPI tile opens its tab.
		await page.getByTestId('c360-kpi-sites').click()
		await expect(p360.tab('Facilities')).toHaveAttribute('aria-selected', 'true')
		await page.getByTestId('c360-kpi-orders').click()
		await expect(p360.tab('Orders')).toHaveAttribute('aria-selected', 'true')

		// A new pick starts on the Overview, and a second search shows its results.
		await p360.search(fx.b_mfl)
		await p360.results.getByTestId('c360-facility-result').first().click()
		await expect(p360.scopeBar).toContainText(fx.b_name)
		await expect(p360.scopeOption('This facility')).toBeChecked()
		await expect(p360.tab('Overview')).toHaveAttribute('aria-selected', 'true')
		await expect(page).not.toHaveURL(/tab=/)
		await p360.openTab('Billing')
		await expect(p360.rows('invoice')).toHaveCount(1)
		await expect(p360.rows('invoice').first()).toContainText(fx.b_invoice)
		await p360.openTab('Orders')
		await expect(p360.rows('order')).toHaveCount(1)
		await expect(p360.rows('order').first()).toContainText(fx.b_order)
	})

	test('the owner organization view uses the same tabs', async ({ page }) => {
		const p360 = new Customer360Page(page)
		await p360.goto()
		await p360.search(fx.organization)
		await p360.openOrganization(fx.organization)
		await expect(page).toHaveURL(/organization=/)
		await expect(p360.scopeBar).toBeHidden()
		await expect(p360.kpiSection).toBeVisible()
		await expect(page.getByText(fx.organization).first()).toBeVisible()
		await p360.openTab('Orders')
		await expect(p360.rows('order')).toHaveCount(2)
		await expect(page.getByTestId('c360-orders').getByRole('columnheader', { name: 'Facility' })).toBeVisible()
		await p360.openTab('Facilities')
		await expect(p360.rows('facility')).toHaveCount(2)
	})

	test('facility scope at every viewport', async ({ page }) => {
		const p360 = new Customer360Page(page)
		for (const viewport of VIEWPORTS) {
			await page.setViewportSize({ width: viewport.width, height: viewport.height })
			await p360.goto(`/crm/customer-360?facility=${fx.a_facility}&scope=facility`)
			await expect(p360.scopeBar).toContainText(fx.a_name)
			await p360.openTab('Quotes')
			await expect(p360.rows('quote')).toHaveCount(10)
			// The scope bar, its toggle and the tab list fit the viewport (tabs scroll sideways).
			const box = await p360.scopeBar.boundingBox()
			expect(box && box.x + box.width).toBeLessThanOrEqual(viewport.width + 1)
			const toggle = await p360.scopeOption('All facilities').boundingBox()
			expect(toggle && toggle.x + toggle.width).toBeLessThanOrEqual(viewport.width + 1)
			const tabs = await page.getByTestId('c360-tabs').boundingBox()
			expect(tabs && tabs.x + tabs.width).toBeLessThanOrEqual(viewport.width + 1)
			expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width + 1)
			// Rows stay on one line; a narrow table scrolls sideways inside its card instead of wrapping.
			const row = await p360.rows('quote').first().boundingBox()
			expect(row && row.height).toBeLessThan(56)
			await shot(page, `c360-4-facility-${viewport.name}`)
		}
	})
})
