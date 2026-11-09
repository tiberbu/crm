// Plan-aware helpers for the customer portal (cx-facility-page-ui SPEC 5.4, 5.5, 7.2, 8.1).
// The server owns the commercial projection; these helpers only shape the view.
import { invoiceStatus, packageLabel } from './portalOrderState'
import { tokenBalanceText } from './tokenBalance'

export function money(amount, currency, defaultCurrency = 'KES') {
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: currency || defaultCurrency,
    currencyDisplay: 'code',
    maximumFractionDigits: 0,
  }).format(amount || 0)
}

function emptyPlan() {
  return {
    name: '',
    source: 'none',
    status: '',
    cycle: '',
    cycle_label: '',
    term_years: null,
    term_label: '',
    currency: '',
    facilities_on_plan: null,
    facility_monthly_excl_vat: null,
    facility_annual_excl_vat: null,
    cycle_amount_incl_vat: null,
    current_period: null,
    next_invoice: null,
    schedule: [],
  }
}

// Normalized commercial projection; legacy fallback per SPEC 5.4 when absent.
export function commercialOf(facility) {
  const raw = facility?.commercial
  if (raw && typeof raw === 'object' && (raw.journey || raw.plan_type)) {
    return {
      journey: raw.journey || 'unknown',
      journey_label: raw.journey_label || '',
      plan_type: raw.plan_type || 'unknown',
      has_tokens: Boolean(raw.has_tokens),
      unavailable: Boolean(raw.unavailable),
      plan: raw.plan && typeof raw.plan === 'object' ? raw.plan : emptyPlan(),
      quotes: Array.isArray(raw.quotes) ? raw.quotes : [],
    }
  }
  const hasToken = Boolean(facility?.token_package) || Number(facility?.token_quantity) > 0
  return {
    journey: 'unknown',
    journey_label: '',
    plan_type: hasToken ? 'token' : 'unknown',
    has_tokens: hasToken,
    unavailable: false,
    plan: emptyPlan(),
    quotes: [],
  }
}

export function showsTokens(facility) {
  const commercial = commercialOf(facility)
  return commercial.plan_type === 'token' || commercial.has_tokens
}

export function canTopUp(facility) {
  const commercial = commercialOf(facility)
  // SPEC 5.5, verbatim: showsTokens OR an unknown facility outside the network journey.
  return (
    (commercial.plan_type === 'token' || commercial.has_tokens) ||
    (commercial.plan_type === 'unknown' && commercial.journey !== 'network_optin')
  )
}

// First row wins for each document name (SPEC 8, merged lists).
export function dedupeByName(rows) {
  const seen = new Set()
  const result = []
  for (const row of rows || []) {
    const key = String(row?.name || '')
    if (!key || seen.has(key)) continue
    seen.add(key)
    result.push(row)
  }
  return result
}

// facility_mfls, else the legacy header tag, else [] (SPEC 5.1/5.2).
export function rowFacilityMfls(row) {
  if (Array.isArray(row?.facility_mfls) && row.facility_mfls.length) return row.facility_mfls
  const legacy = String(row?.crm_token_facility_mfl || '').trim()
  return legacy ? [legacy] : []
}

export function rowsForFacility(rows, mfl) {
  const key = String(mfl || '').trim().toLowerCase()
  if (!key) return []
  return (rows || []).filter((row) =>
    rowFacilityMfls(row).some((value) => String(value).toLowerCase() === key),
  )
}

// Rows not tied to any facility (SPEC 8 notice).
export function accountLevelRows(rows) {
  return (rows || []).filter((row) => rowFacilityMfls(row).length === 0)
}

function dedupeRowsByName(a, b) {
  const seen = new Set()
  const result = []
  for (const row of [...(a || []), ...(b || [])]) {
    const key = String(row?.name || '')
    if (!key || seen.has(key)) continue
    seen.add(key)
    result.push(row)
  }
  return result
}

export function mergeFacilityOrders(facility, allOrders) {
  const merged = dedupeRowsByName(facility?.orders, rowsForFacility(allOrders, facility?.mfl_code))
  return merged.sort((a, b) => {
    const da = String(a.transaction_date || a.creation || '')
    const db = String(b.transaction_date || b.creation || '')
    if (da !== db) return da < db ? 1 : -1
    return String(b.name || '').localeCompare(String(a.name || ''))
  })
}

export function mergeFacilityInvoices(facility, allInvoices) {
  return dedupeRowsByName(facility?.invoices, rowsForFacility(allInvoices, facility?.mfl_code))
}

export function facilityPayments(facility, allPayments, invoices) {
  const invoiceNames = new Set((invoices || []).map((invoice) => String(invoice?.name || '')))
  const pendingFromAccount = (allPayments || []).filter((payment) => {
    if (payment.status !== 'Pending Verification') return false
    const names = payment.invoice_names?.length
      ? payment.invoice_names
      : payment.invoice
        ? [payment.invoice]
        : []
    return names.some((name) => invoiceNames.has(String(name)))
  })
  const key = (payment) => `${payment.name}:${payment.invoice || ''}`
  const seen = new Set()
  const result = []
  for (const payment of [...(facility?.payments || []), ...pendingFromAccount]) {
    const id = key(payment)
    if (seen.has(id)) continue
    seen.add(id)
    result.push(payment)
  }
  return result
}

// Open invoices first by due date, then paid newest first (SPEC 7.2).
export function sortInvoices(invoices, today = new Date()) {
  const open = []
  const paid = []
  for (const invoice of invoices || []) {
    if (Number(invoice?.amount) > 0) open.push(invoice)
    else paid.push(invoice)
  }
  open.sort((a, b) => {
    const da = String(a.due_date || '')
    const db = String(b.due_date || '')
    if (da !== db) return da < db ? -1 : 1
    return Number(invoiceStatus(a, today).key === 'overdue') - Number(invoiceStatus(b, today).key === 'overdue')
  })
  paid.sort((a, b) => String(b.posting_date || '').localeCompare(String(a.posting_date || '')))
  return [...open, ...paid]
}

export function orderTitle(order, packages) {
  return order?.display_title || packageLabel(order?.crm_token_package_item, packages) || 'Order'
}

export function orderStatus(order) {
  return order?.display_status || (order?.is_draft ? 'Needs your review' : 'Awaiting invoice')
}

// counts: the facility row's record_counts (S4). The context row only carries
// actionable records, so counts say whether any (paid) history exists.
function stageState(key, quotes, orders, invoices, payments, counts = {}) {
  if (key === 'quote') {
    if (quotes.some((quote) => quote.status_label === 'Accepted')) return 'done'
    return quotes.length ? 'pending' : 'upcoming'
  }
  if (key === 'order') {
    const hasDraft = orders.some((order) => order.is_draft) || Number(counts.order_draft) > 0
    if (hasDraft) return 'pending'
    return orders.length || Number(counts.order) > 0 ? 'done' : 'upcoming'
  }
  const anyDue = invoices.some((invoice) => Number(invoice.amount) > 0) || Number(counts.invoice_due) > 0
  if (key === 'invoice') {
    const anyInvoice = invoices.length > 0 || Number(counts.invoice) > 0
    if (anyInvoice && !anyDue) return 'done'
    return anyDue ? 'pending' : 'upcoming'
  }
  const pendingReport =
    payments.some((payment) => payment.status === 'Pending Verification') || Number(counts.payment_pending) > 0
  const anyPayment = payments.length > 0 || Number(counts.payment) > 0
  if (anyPayment && !pendingReport && !anyDue) return 'done'
  if (pendingReport || (anyPayment && anyDue)) return 'pending'
  return 'upcoming'
}

// SPEC 7.2 stage states; returns the ordered visible stages with final state.
export function stageStates({ showQuote, quotes, orders, invoices, payments, counts }) {
  const stages = []
  if (showQuote) stages.push({ key: 'quote', title: 'Quotes', rows: quotes || [] })
  stages.push({ key: 'order', title: 'Orders', rows: orders || [] })
  stages.push({ key: 'invoice', title: 'Invoices', rows: invoices || [] })
  stages.push({ key: 'payment', title: 'Payments', rows: payments || [] })
  const states = stages.map((stage) =>
    stageState(stage.key, quotes || [], orders || [], invoices || [], payments || [], counts || {}),
  )
  let firstPending = states.findIndex((state) => state === 'pending')
  if (firstPending === -1) {
    const firstUpcoming = states.findIndex((state) => state === 'upcoming')
    if (firstUpcoming !== -1) states[firstUpcoming] = 'current'
  } else {
    states[firstPending] = 'current'
    for (let i = firstPending + 1; i < states.length; i += 1) {
      if (states[i] === 'pending') states[i] = 'upcoming'
    }
  }
  return stages.map((stage, index) => ({ ...stage, state: states[index] }))
}

// The quote → order → invoice → payment stepper only teaches the first purchase.
// Once the facility has completed the cycle (a paid invoice or a recorded payment),
// it is hidden: with documents at different stages a single "current step" misleads,
// and the tab badges say what is waiting instead.
export function journeyCompleted({ invoices = [], payments = [], counts = null } = {}) {
  if (counts) {
    if (Number(counts.invoice) > Number(counts.invoice_due || 0)) return true
    if (Number(counts.payment) > Number(counts.payment_pending || 0)) return true
  }
  if ((invoices || []).some((invoice) => Number(invoice?.amount) <= 0)) return true
  return (payments || []).some((payment) => payment && payment.status !== 'Pending Verification')
}

export function capRows(rows, expanded, limit = 5) {
  return expanded ? rows : rows.slice(0, limit)
}

// Parse date-only values as local dates so 2027-01-30 never shifts a day (SPEC 8.1).
export function formatDate(value) {
  if (value === null || value === undefined || value === '') return ''
  const text = String(value).trim()
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})/)
  let date
  if (match) date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
  else {
    date = new Date(text.replace(' ', 'T'))
    if (Number.isNaN(date.getTime())) return text
  }
  return date.toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' })
}

export function isProjected(invoiceLike) {
  return Boolean(invoiceLike?.projected)
}

// SPEC 8.1 helper rows.
export function facilityPlanText(facility) {
  const commercial = commercialOf(facility)
  if (commercial.plan_type === 'token') {
    return [facility?.token_package || 'No active plan']
  }
  if (commercial.plan_type === 'unknown') return ['No active plan']
  const lines = [commercial.plan.name]
  if (commercial.plan.cycle_label) lines.push(commercial.plan.cycle_label)
  return lines.filter(Boolean)
}

export function balanceOrNextLabel(facility) {
  const commercial = commercialOf(facility)
  if (commercial.plan_type === 'time_bound') return 'Next invoice'
  if (commercial.plan_type === 'token') return 'Available tokens'
  return 'Plan'
}

export function balanceOrNextText(facility) {
  const commercial = commercialOf(facility)
  if (commercial.plan_type === 'token') return tokenBalanceText(facility)
  if (commercial.plan_type === 'unknown') return 'Not set up yet'
  const next = commercial.plan.next_invoice
  if (!next?.date) return 'Not scheduled'
  const prefix = next.projected ? 'Projected ' : ''
  return `${prefix}${formatDate(next.date)}`
}

export function portfolioPlanSummary(facilities) {
  const list = facilities || []
  let tokenFacilities = 0
  let planFacilities = 0
  let nextInvoice = null
  for (const facility of list) {
    const commercial = commercialOf(facility)
    if (showsTokens(facility)) tokenFacilities += 1
    if (commercial.plan_type === 'time_bound') {
      planFacilities += 1
      const next = commercial.plan.next_invoice
      if (next?.date && (!nextInvoice || String(next.date) < String(nextInvoice.date))) {
        nextInvoice = { date: next.date, amount: next.amount_incl_vat, projected: Boolean(next.projected) }
      }
    }
  }
  return { tokenFacilities, planFacilities, nextInvoice }
}

export function portfolioColumnLabel(facilities) {
  const summary = portfolioPlanSummary(facilities)
  if (summary.tokenFacilities > 0 && summary.planFacilities > 0) return 'Tokens or next invoice'
  if (summary.tokenFacilities > 0) return 'Available tokens'
  return 'Next invoice'
}
