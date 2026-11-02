import { describe, expect, test } from 'vitest'
import {
	invoiceState,
	onboardingState,
	paidState,
	partnerKindLabel,
	provisioningHeadline,
	siteState,
} from '@/utils/customer360.js'

describe('invoiceState', () => {
	test('submitted invoice with no outstanding is Paid', () => {
		expect(invoiceState({ docstatus: 1, outstanding: 0 })).toEqual({
			label: 'Paid',
			theme: 'green',
		})
	})

	test('submitted invoice with outstanding and past due is Overdue', () => {
		expect(
			invoiceState({ docstatus: 1, outstanding: 500, days_overdue: 12 })
		).toEqual({ label: 'Overdue', theme: 'red' })
	})

	test('submitted invoice with outstanding but not due is Unpaid', () => {
		expect(
			invoiceState({ docstatus: 1, outstanding: 500, days_overdue: 0 })
		).toEqual({ label: 'Unpaid', theme: 'amber' })
	})

	test('draft invoice is Draft', () => {
		expect(invoiceState({ docstatus: 0 })).toEqual({
			label: 'Draft',
			theme: 'gray',
		})
	})
})

describe('siteState', () => {
	test('opted-in and go-live membership is Live', () => {
		expect(siteState({ status: 'Opted In', opted_in: true, go_live: true })).toEqual({
			label: 'Live',
			theme: 'green',
		})
	})

	test('opted-in without go-live is Opted In', () => {
		expect(siteState({ status: 'Opted In', opted_in: true, go_live: false })).toEqual({
			label: 'Opted In',
			theme: 'blue',
		})
	})

	test('declined membership is Declined', () => {
		expect(siteState({ status: 'Declined' })).toEqual({
			label: 'Declined',
			theme: 'gray',
		})
	})

	test('plain active membership is Active', () => {
		expect(siteState({ status: 'Active' })).toEqual({
			label: 'Active',
			theme: 'amber',
		})
	})
})

describe('provisioningHeadline', () => {
	test('no sites', () => {
		expect(provisioningHeadline({ sites_total: 0, sites_live: 0 })).toBe('No sites')
	})

	test('all live', () => {
		expect(provisioningHeadline({ sites_total: 3, sites_live: 3 })).toBe('All live')
	})

	test('partial', () => {
		expect(provisioningHeadline({ sites_total: 4, sites_live: 2 })).toBe('2 of 4 live')
	})
})

describe('paidState', () => {
	test('paid', () => {
		expect(paidState({ package_paid: true })).toEqual({ label: 'Yes', theme: 'green' })
	})

	test('not paid', () => {
		expect(paidState({ package_paid: false })).toEqual({ label: 'No', theme: 'gray' })
	})
})

describe('partnerKindLabel', () => {
	test('network', () => {
		expect(partnerKindLabel('network')).toBe('Partner Network')
	})

	test('legacy', () => {
		expect(partnerKindLabel('legacy')).toBe('Partner')
	})
})

describe('onboardingState', () => {
	test('complete is Provisioned', () => {
		expect(onboardingState({ status: 'Complete' })).toEqual({
			label: 'Provisioned',
			theme: 'green',
		})
	})

	test('in progress stays visible', () => {
		expect(onboardingState({ status: 'In Progress' })).toEqual({
			label: 'In Progress',
			theme: 'blue',
		})
	})

	test('defaults to Submitted', () => {
		expect(onboardingState({})).toEqual({ label: 'Submitted', theme: 'amber' })
	})
})
