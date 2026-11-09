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

/**
 * Display state for one quotation row.
 * quote: { docstatus, status }
 */
export function quoteState(quote = {}) {
	if (quote.docstatus === 2 || quote.status === 'Cancelled') {
		return { label: 'Cancelled', theme: 'gray' }
	}
	if (quote.docstatus !== 1) {
		return { label: 'Draft', theme: 'gray' }
	}
	if (quote.status === 'Ordered') return { label: 'Ordered', theme: 'green' }
	if (quote.status === 'Lost') return { label: 'Lost', theme: 'red' }
	if (quote.status === 'Expired') return { label: 'Expired', theme: 'gray' }
	return { label: quote.status || 'Open', theme: 'blue' }
}

/**
 * Facility names for a record's attributed MFL codes (organization view's Facility column).
 * Unknown codes are shown as-is; a record tied to no facility reads "—".
 */
export function facilityLabelFor(mfls = [], facilities = []) {
	const names = new Map(
		(facilities || []).map((f) => [String(f.mfl_code || '').trim().toLowerCase(), f.facility_name]),
	)
	const labels = (mfls || [])
		.map((mfl) => String(mfl || '').trim())
		.filter(Boolean)
		.map((mfl) => names.get(mfl.toLowerCase()) || mfl)
	return labels.length ? [...new Set(labels)].join(', ') : '—'
}

/**
 * Records left out of the facility view because they are tied to no facility.
 * scope: { mode, unattributed: { orders, quotes, invoices } }
 */
export function unattributedCount(scope = {}) {
	if (scope?.mode !== 'facility') return 0
	const counts = scope.unattributed || {}
	return (counts.orders || 0) + (counts.quotes || 0) + (counts.invoices || 0)
}

const SCOPES = ['facility', 'organization']

/**
 * The page's selection from the route query. A facility wins over a deal, a deal over an
 * organization; a facility's scope defaults to "facility".
 * Returns null when nothing is selected.
 */
export function selectionFromQuery(query = {}) {
	const pick = (key) => {
		const value = Array.isArray(query[key]) ? query[key][0] : query[key]
		return String(value || '').trim()
	}
	if (pick('facility')) {
		const scope = SCOPES.includes(pick('scope')) ? pick('scope') : 'facility'
		return { kind: 'facility', name: pick('facility'), scope }
	}
	if (pick('deal')) return { kind: 'deal', name: pick('deal') }
	if (pick('organization')) return { kind: 'organization', name: pick('organization') }
	return null
}

/**
 * The route query for a selection (inverse of selectionFromQuery).
 */
export function queryForSelection(selection) {
	if (!selection?.name) return {}
	if (selection.kind === 'facility') {
		return { facility: selection.name, scope: selection.scope === 'organization' ? 'organization' : 'facility' }
	}
	return { [selection.kind]: selection.name }
}

/**
 * The get_customer_360 params for a selection.
 */
export function paramsForSelection(selection) {
	if (!selection?.name) return null
	if (selection.kind === 'facility') {
		return { facility: selection.name, scope: selection.scope || 'facility' }
	}
	return { [selection.kind]: selection.name }
}

/** Tab order on the 360 view (party record T2). */
export const TABS = ['overview', 'orders', 'quotes', 'billing', 'facilities', 'deals']

/** A valid tab key from a route query value; anything else is the Overview. */
export function tabFromQuery(value) {
	const key = String((Array.isArray(value) ? value[0] : value) || '').trim()
	return TABS.includes(key) ? key : 'overview'
}

export const PAGE_SIZE = 10

/**
 * One page of rows plus its label data. Out-of-range pages clamp to the last page.
 * Returns { rows, page, pages, start, end, total }.
 */
export function paginate(rows = [], page = 1, size = PAGE_SIZE) {
	const list = rows || []
	const total = list.length
	const pages = Math.max(1, Math.ceil(total / size))
	const current = Math.min(Math.max(1, Number(page) || 1), pages)
	const offset = (current - 1) * size
	return {
		rows: list.slice(offset, offset + size),
		page: current,
		pages,
		start: total ? offset + 1 : 0,
		end: Math.min(offset + size, total),
		total,
	}
}

/**
 * The Overview's "Needs attention" list: up to `limit` outstanding submitted invoices
 * (most overdue first) and up to `limit` open orders.
 */
export function needsAttention(data = {}, limit = 3) {
	const invoices = (data?.invoices || [])
		.filter((inv) => inv.docstatus === 1 && (inv.outstanding || 0) > 0)
		.sort((a, b) => (b.days_overdue || 0) - (a.days_overdue || 0))
	const orders = (data?.orders || []).filter((order) => order.open)
	return {
		invoices: invoices.slice(0, limit),
		invoiceTotal: invoices.length,
		orders: orders.slice(0, limit),
		orderTotal: orders.length,
	}
}
