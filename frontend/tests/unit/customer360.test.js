import { describe, expect, test } from 'vitest'
import {
	TABS,
	facilityLabelFor,
	needsAttention,
	paginate,
	tabFromQuery,
	invoiceState,
	onboardingState,
	paidState,
	partnerKindLabel,
	paramsForSelection,
	provisioningHeadline,
	queryForSelection,
	quoteState,
	selectionFromQuery,
	siteState,
	unattributedCount,
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

describe('quoteState', () => {
	test('draft and cancelled quotes are gray', () => {
		expect(quoteState({ docstatus: 0 })).toEqual({ label: 'Draft', theme: 'gray' })
		expect(quoteState({ docstatus: 2, status: 'Cancelled' })).toEqual({ label: 'Cancelled', theme: 'gray' })
	})

	test('submitted quotes follow their status', () => {
		expect(quoteState({ docstatus: 1, status: 'Ordered' }).theme).toBe('green')
		expect(quoteState({ docstatus: 1, status: 'Lost' }).theme).toBe('red')
		expect(quoteState({ docstatus: 1, status: 'Open' })).toEqual({ label: 'Open', theme: 'blue' })
	})
})

describe('facilityLabelFor', () => {
	const facilities = [
		{ mfl_code: '11111', facility_name: 'West Clinic' },
		{ mfl_code: 'ab-22', facility_name: 'East Clinic' },
	]

	test('maps attributed codes to facility names, case-insensitively', () => {
		expect(facilityLabelFor(['11111'], facilities)).toBe('West Clinic')
		expect(facilityLabelFor(['AB-22', '11111'], facilities)).toBe('East Clinic, West Clinic')
	})

	test('unknown codes show as-is and no code reads as a dash', () => {
		expect(facilityLabelFor(['99999'], facilities)).toBe('99999')
		expect(facilityLabelFor([], facilities)).toBe('—')
		expect(facilityLabelFor(undefined, undefined)).toBe('—')
	})
})

describe('unattributedCount', () => {
	test('sums the records left out of the facility view', () => {
		expect(
			unattributedCount({ mode: 'facility', unattributed: { orders: 1, quotes: 0, invoices: 2 } }),
		).toBe(3)
	})

	test('is zero outside the facility view', () => {
		expect(
			unattributedCount({ mode: 'organization', unattributed: { invoices: 2 } }),
		).toBe(0)
		expect(unattributedCount(undefined)).toBe(0)
	})
})

describe('selection <-> route query', () => {
	test('a facility wins and defaults to the facility scope', () => {
		expect(selectionFromQuery({ facility: 'F1', deal: 'D1' })).toEqual({
			kind: 'facility',
			name: 'F1',
			scope: 'facility',
		})
		expect(selectionFromQuery({ facility: 'F1', scope: 'organization' }).scope).toBe('organization')
		expect(selectionFromQuery({ facility: 'F1', scope: 'bogus' }).scope).toBe('facility')
	})

	test('deal and organization selections, or nothing', () => {
		expect(selectionFromQuery({ deal: ' D1 ' })).toEqual({ kind: 'deal', name: 'D1' })
		expect(selectionFromQuery({ organization: ['acme'] })).toEqual({ kind: 'organization', name: 'acme' })
		expect(selectionFromQuery({})).toBeNull()
	})

	test('query and params round-trip', () => {
		const selection = { kind: 'facility', name: 'F1', scope: 'organization' }
		expect(selectionFromQuery(queryForSelection(selection))).toEqual(selection)
		expect(paramsForSelection(selection)).toEqual({ facility: 'F1', scope: 'organization' })
		expect(paramsForSelection({ kind: 'deal', name: 'D1' })).toEqual({ deal: 'D1' })
		expect(queryForSelection(null)).toEqual({})
		expect(paramsForSelection(null)).toBeNull()
	})
})

describe('tabs', () => {
	test('known tab keys pass, anything else is the overview', () => {
		expect(TABS[0]).toBe('overview')
		expect(tabFromQuery('billing')).toBe('billing')
		expect(tabFromQuery(['quotes'])).toBe('quotes')
		expect(tabFromQuery('nope')).toBe('overview')
		expect(tabFromQuery(undefined)).toBe('overview')
	})
})

describe('paginate', () => {
	const rows = Array.from({ length: 23 }, (_, i) => i + 1)

	test('pages of ten with a label range', () => {
		expect(paginate(rows, 1)).toMatchObject({ page: 1, pages: 3, start: 1, end: 10, total: 23 })
		expect(paginate(rows, 3).rows).toEqual([21, 22, 23])
		expect(paginate(rows, 3)).toMatchObject({ start: 21, end: 23 })
	})

	test('out-of-range pages clamp and empty lists read 0 of 0', () => {
		expect(paginate(rows, 9).page).toBe(3)
		expect(paginate(rows, 0).page).toBe(1)
		expect(paginate([], 1)).toMatchObject({ rows: [], page: 1, pages: 1, start: 0, end: 0, total: 0 })
		expect(paginate(undefined).total).toBe(0)
	})
})

describe('needsAttention', () => {
	test('outstanding submitted invoices, most overdue first, and open orders', () => {
		const data = {
			invoices: [
				{ name: 'A', docstatus: 1, outstanding: 10, days_overdue: 2 },
				{ name: 'B', docstatus: 1, outstanding: 0 },
				{ name: 'C', docstatus: 0, outstanding: 50 },
				{ name: 'D', docstatus: 1, outstanding: 5, days_overdue: 30 },
			],
			orders: [{ name: 'O1', open: true }, { name: 'O2', open: false }],
		}
		const result = needsAttention(data)
		expect(result.invoices.map((i) => i.name)).toEqual(['D', 'A'])
		expect(result.invoiceTotal).toBe(2)
		expect(result.orders.map((o) => o.name)).toEqual(['O1'])
	})

	test('caps each list and tolerates missing data', () => {
		const orders = Array.from({ length: 5 }, (_, i) => ({ name: `O${i}`, open: true }))
		expect(needsAttention({ orders }).orders).toHaveLength(3)
		expect(needsAttention({ orders }).orderTotal).toBe(5)
		expect(needsAttention(undefined)).toEqual({ invoices: [], invoiceTotal: 0, orders: [], orderTotal: 0 })
	})
})
