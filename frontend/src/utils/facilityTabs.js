// Tabs and paging for the CX facility page (docs/cx-facility-page-tabs-and-registry-notice-fixes.md).
// Pure helpers so the tab set, the index <-> key mapping (frappe-ui 1.0.0-beta.24 Tabs
// is index-based) and local paging are unit-tested without mounting components.

export const DOCUMENT_PAGE_SIZE = 20

const TAB_LABELS = {
  overview: 'Overview',
  usage: 'Usage',
  schedule: 'Payment schedule',
  quote: 'Quotes',
  order: 'Orders',
  invoice: 'Invoices',
  payment: 'Payments',
  billing: 'Billing',
}

// Action badge per tab: what still needs the customer's attention on that tab. With
// several documents at different stages, each tab says what is waiting there.
const BADGES = {
  order: { countKey: 'orderDraft', text: (n) => `${n} to review` },
  invoice: { countKey: 'invoiceDue', text: (n) => `${n} due` },
  payment: { countKey: 'paymentPending', text: (n) => `${n} pending` },
}

// counts: { quote, order, orderDraft, invoice, invoiceDue, payment, paymentPending };
// a missing count renders no number.
// showSchedule: Network Opt-In facilities get the contract's Payment schedule (ledger) tab.
// showUsage: token-plan facilities with an FID get the Usage report tab (P-135).
export function facilityTabs({ showQuote = false, showSchedule = false, showUsage = false, counts = {} } = {}) {
  const keys = [
    'overview',
    ...(showUsage ? ['usage'] : []),
    ...(showSchedule ? ['schedule'] : []),
    ...(showQuote ? ['quote'] : []),
    'order',
    'invoice',
    'payment',
    'billing',
  ]
  return keys.map((key) => {
    const count = Number.isFinite(counts[key]) ? counts[key] : null
    const rule = BADGES[key]
    const waiting = rule ? Number(counts[rule.countKey]) || 0 : 0
    return { key, label: TAB_LABELS[key], count, badge: waiting > 0 ? rule.text(waiting) : '' }
  })
}

export function tabIndex(tabs, key) {
  const index = (tabs || []).findIndex((tab) => tab.key === key)
  return index >= 0 ? index : 0
}

export function tabKey(tabs, index) {
  return tabs?.[Number(index)]?.key || 'overview'
}

function searchable(row) {
  return [
    row?.name,
    row?.invoice_number,
    row?.reference_no,
    row?.display_title,
    row?.label,
    row?.quotation,
    ...(row?.sales_orders || []),
    ...(row?.invoice_names || []),
  ]
    .filter(Boolean)
    .map((value) => String(value).toLowerCase())
}

export function filterRows(rows, { kind, status = 'all', search = '' } = {}) {
  let result = rows || []
  if (kind === 'invoice' && status === 'outstanding') {
    result = result.filter((row) => Number(row?.amount) > 0)
  }
  const needle = String(search || '').trim().toLowerCase()
  if (needle) result = result.filter((row) => searchable(row).some((value) => value.includes(needle)))
  return result
}

export function pageCount(total, size = DOCUMENT_PAGE_SIZE) {
  return Math.max(1, Math.ceil((Number(total) || 0) / size))
}

export function clampPage(page, total, size = DOCUMENT_PAGE_SIZE) {
  return Math.min(Math.max(0, Number(page) || 0), pageCount(total, size) - 1)
}

export function pageSlice(rows, page, size = DOCUMENT_PAGE_SIZE) {
  const start = clampPage(page, (rows || []).length, size) * size
  return (rows || []).slice(start, start + size)
}

// 0-based page holding the row, or -1 when it is not in the list.
export function pageOfRow(rows, name, size = DOCUMENT_PAGE_SIZE) {
  const index = (rows || []).findIndex((row) => String(row?.name) === String(name))
  return index < 0 ? -1 : Math.floor(index / size)
}

export function rangeText(page, total, size = DOCUMENT_PAGE_SIZE) {
  if (!total) return 'No records'
  const start = clampPage(page, total, size) * size
  return `Showing ${start + 1}–${Math.min(start + size, total)} of ${total}`
}
