import { Page, expect } from '@playwright/test'

export class Customer360Page {
	constructor(private page: Page) {}

	async goto(): Promise<void> {
		await this.page.goto('/crm/customer-360')
		await this.page.waitForLoadState('networkidle')
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
		await expect(
			this.page.locator('.mx-6.mt-4'),
		).toBeVisible({ timeout: 15000 })
	}

	async openOrganization(label: string): Promise<void> {
		await this.page
			.getByRole('button', { name: new RegExp(`Open 360 for ${label}`) })
			.first()
			.click()
	}

	async openDeal(dealName: string): Promise<void> {
		await this.page
			.getByRole('button', { name: new RegExp(`Open 360 for ${dealName}`) })
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
