import { Page, expect } from '@playwright/test'

/** Names such as "Clinic (synthetic)" must match literally. */
function escapeRegExp(value: string): string {
	return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export class Customer360Page {
	constructor(private page: Page) {}

	async goto(path = '/crm/customer-360'): Promise<void> {
		await this.page.goto(path)
		await this.page.waitForLoadState('networkidle')
		await this.dismissGettingStarted()
	}

	/** A new user's "Getting started" panel floats over the page's right edge; close it. */
	async dismissGettingStarted(): Promise<void> {
		const panel = this.page.locator('.fixed.z-50.w-80').filter({ hasText: 'Getting started' })
		if (await panel.isVisible().catch(() => false)) {
			await panel.getByRole('button').nth(1).click()
			await panel.waitFor({ state: 'hidden' }).catch(() => {})
		}
	}

	get searchInput() {
		return this.page.getByPlaceholder(/Search organization/)
	}

	/**
	 * Type into the debounced search box and wait for results to land.
	 * The page debounces 600ms, so assertions must tolerate the delay.
	 */
	async search(query: string): Promise<void> {
		await this.searchInput.fill(query)
		await expect(this.results).toBeVisible({ timeout: 15000 })
	}

	/** The search results dropdown. */
	get results() {
		return this.page.getByTestId('c360-results')
	}

	get clearButton() {
		return this.page.getByTestId('c360-search-clear')
	}

	get closeResultsButton() {
		return this.page.getByTestId('c360-results-close')
	}

	get scopeBar() {
		return this.page.getByTestId('c360-scope-bar')
	}

	/** "This facility" / "All facilities" in the facility scope bar. */
	scopeOption(label: 'This facility' | 'All facilities') {
		return this.scopeBar.getByRole('radio', { name: label })
	}

	rows(kind: 'order' | 'quote' | 'invoice' | 'payment' | 'facility') {
		return this.page.getByTestId(`c360-${kind}-row`)
	}

	async openOrganization(label: string): Promise<void> {
		await this.page
			.getByRole('button', { name: new RegExp(`Open 360 for ${escapeRegExp(label)}`) })
			.first()
			.click()
	}

	async openDeal(dealName: string): Promise<void> {
		await this.page
			.getByRole('button', { name: new RegExp(`Open 360 for ${escapeRegExp(dealName)}`) })
			.first()
			.click()
	}

	async openFacility(label: string): Promise<void> {
		await this.page
			.getByRole('button', { name: new RegExp(`Open 360 for ${escapeRegExp(label)}`) })
			.first()
			.click()
	}

	get kpiSection() {
		return this.page.getByText('Package Paid', { exact: true })
	}

	get customerSection() {
		return this.page.getByText('Customer', { exact: true }).first()
	}

	get partnerSection() {
		return this.page.getByText('Partner Details', { exact: true })
	}

	get billingSection() {
		return this.page.getByText('Billing', { exact: true }).first()
	}

	get facilitiesSection() {
		return this.page.getByText('Facilities & Provisioning', { exact: true })
	}
}

export class DealCustomer360 {
	constructor(private page: Page) {}

	async openDeal(dealId: string): Promise<void> {
		await this.page.goto(`/crm/deals/${dealId}`)
		await this.page.waitForLoadState('networkidle')
	}

	async open360Tab(): Promise<void> {
		await this.page.getByRole('tab', { name: 'Customer 360' }).click()
	}
}
