// Opt-In billing ledger: display rules for the payment schedule and paying ahead
// (_bmad-output/optin-billing-ledger/planning-artifacts/spec-optin-billing-ledger.md).
// The server decides states and limits; these helpers only present them.

// Status colours are semantic only: due/overdue need action, paid is done, a failed row needs us.
const TONES = {
  due: 'warning',
  overdue: 'danger',
  paid: 'success',
  paid_ahead: 'success',
  needs_attention: 'danger',
}

export function stateTone(state) {
  return TONES[state] || 'neutral'
}

const TONE_CLASSES = {
  warning: 'border-cx-warning-border bg-cx-warning-soft text-cx-warning-ink',
  danger: 'border-cx-danger-border bg-cx-danger-soft text-cx-danger-ink',
  success: 'border-cx-success-border bg-cx-success-soft text-cx-success-ink',
  neutral: 'border-cx-border bg-cx-well text-cx-ink-2',
}

export function stateClasses(state) {
  return TONE_CLASSES[stateTone(state)]
}

// What the row's action is: pay an issued invoice, or nothing (issuing is the pay-ahead card).
export function periodAction(period) {
  if (!period?.sales_invoice) return ''
  if (Number(period.outstanding) <= 0) return ''
  if ((period.payments || []).some((payment) => payment.status === 'Pending verification')) return 'pending'
  return 'pay'
}

// The invoice row the portal's payment modal expects.
export function payableInvoice(source, oisName, currency = 'KES') {
  const name = source?.sales_invoice || source?.name
  const outstanding = Number(source?.outstanding) || 0
  return {
    name,
    invoice_number: name,
    amount: outstanding,
    outstanding_amount: outstanding,
    grand_total: Number(source?.invoice_total ?? source?.amount) || outstanding,
    currency: source?.currency || currency,
    due_date: source?.due_date || '',
    ois_name: oisName,
  }
}

// The first period still waiting for its invoice date, for the "Next invoice" panel (P-134).
export function nextScheduledPeriod(years) {
  for (const year of years || []) {
    for (const period of year?.periods || []) {
      if (!period?.sales_invoice) {
        return {
          label: period.label,
          amount: Number(period.amount) || 0,
          scheduled_date: period.scheduled_date || '',
          due_date: period.due_date || '',
        }
      }
    }
  }
  return null
}

export function advanceTotal(next, count) {
  return (next || []).slice(0, Math.max(Number(count) || 0, 0)).reduce((sum, row) => sum + (Number(row.amount) || 0), 0)
}

export function advanceLabels(next, count) {
  return (next || []).slice(0, Math.max(Number(count) || 0, 0)).map((row) => row.label)
}

// "Year 1 · Q1 – Year 1 · Q3" for a run of periods, or the one label.
export function periodRange(labels) {
  if (!labels?.length) return ''
  return labels.length === 1 ? labels[0] : `${labels[0]} – ${labels[labels.length - 1]}`
}

// Years that still need attention open by default; fully paid years fold away.
export function yearOpenByDefault(year, index) {
  const periods = year?.periods || []
  if (index === 0) return true
  return periods.some((period) => !['paid', 'paid_ahead', 'scheduled'].includes(period.state))
}

export function yearSummary(year) {
  const periods = year?.periods || []
  const paid = periods.filter((period) => period.state === 'paid' || period.state === 'paid_ahead').length
  const total = periods.reduce((sum, period) => sum + (Number(period.amount) || 0), 0)
  return { paid, count: periods.length, total }
}

export function quotationPdfUrl(quotation, { oisNumber = '', customer = '' } = {}) {
  if (!quotation) return ''
  const params = new URLSearchParams({ quotation })
  if (oisNumber) params.set('ois_number', oisNumber)
  else if (customer) params.set('customer', customer)
  return `/api/method/crm.api.optin_ledger.quotation_pdf?${params.toString()}`
}
