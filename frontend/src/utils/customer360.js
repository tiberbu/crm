// Pure helpers for the Customer 360 view.
// Unit-tested in frontend/tests/unit/customer360.test.js.

/**
 * Display state for one invoice row.
 * inv: { docstatus, outstanding, days_overdue }
 */
export function invoiceState(inv = {}) {
	if (inv.docstatus !== 1) {
		return { label: 'Draft', theme: 'gray' }
	}
	if ((inv.outstanding || 0) <= 0) {
		return { label: 'Paid', theme: 'green' }
	}
	if ((inv.days_overdue || 0) > 0) {
		return { label: 'Overdue', theme: 'red' }
	}
	return { label: 'Unpaid', theme: 'amber' }
}

/**
 * Display state for one facility membership row.
 * membership: { status, opted_in, go_live }
 */
export function siteState(membership = {}) {
	if (membership.status === 'Declined') {
		return { label: 'Declined', theme: 'gray' }
	}
	if (membership.opted_in && membership.go_live) {
		return { label: 'Live', theme: 'green' }
	}
	if (membership.opted_in) {
		return { label: 'Opted In', theme: 'blue' }
	}
	return { label: 'Active', theme: 'amber' }
}

/**
 * Headline for the sites KPI tile.
 * summary: { sites_total, sites_live }
 */
export function provisioningHeadline(summary = {}) {
	const total = summary.sites_total || 0
	const live = summary.sites_live || 0
	if (!total) return 'No sites'
	if (live === total) return 'All live'
	return `${live} of ${total} live`
}

/**
 * Display state for the package-paid KPI tile.
 * summary: { package_paid }
 */
export function paidState(summary = {}) {
	return summary.package_paid
		? { label: 'Yes', theme: 'green' }
		: { label: 'No', theme: 'gray' }
}

/**
 * Human label for a partner attribution kind.
 */
export function partnerKindLabel(kind) {
	return kind === 'network' ? 'Partner Network' : 'Partner'
}

/**
 * Display state for an onboarding request row.
 * row: { status, careverse_provisioned_date }
 */
export function onboardingState(row = {}) {
	if (row.status === 'Complete' || row.careverse_provisioned_date) {
		return { label: 'Provisioned', theme: 'green' }
	}
	if (row.status === 'In Progress' || row.status === 'Allocated') {
		return { label: row.status, theme: 'blue' }
	}
	return { label: row.status || 'Submitted', theme: 'amber' }
}
