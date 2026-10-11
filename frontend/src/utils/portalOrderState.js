// Display rules for the Customer Experience portal's order and payment actions.
// The server owns eligibility, pricing and ownership; these helpers only shape the view.

export function findOpenOrder(orders, facilityMfl, itemCode) {
  return (
    (orders || []).find(
      (order) =>
        String(order.crm_token_facility_mfl) === String(facilityMfl) &&
        String(order.crm_token_package_item) === String(itemCode),
    ) || null
  )
}

export function packageLabel(itemCode, packages) {
  const match = (packages || []).find((item) => item.item_code === itemCode)
  return match?.display_name || itemCode || ''
}

export function facilityLabel(mfl, facilities) {
  const match = (facilities || []).find(
    (item) => String(item.mfl_code) === String(mfl),
  )
  return match?.facility_name || mfl || ''
}

// Paystack redirects back to /cx-portal?reference=...; the reference is a selector only.
export function referenceFromSearch(search) {
  const value = new URLSearchParams(search || '').get('reference') || ''
  return /^[A-Za-z0-9._-]{6,120}$/.test(value) ? value : ''
}

// References are created as OIS-<ois>-<invoice>-<nonce>; match against the user's own OIS list.
export function oisForReference(reference, oisNames) {
  const safe = String(reference || '')
  return (
    [...(oisNames || [])]
      .sort((a, b) => b.length - a.length)
      .find((name) => safe.includes(String(name).replace(/\//g, '-'))) || ''
  )
}

export function paymentFailureMessage(error) {
  const text = error?.messages?.[0] || ''
  if (/not configured/i.test(text)) {
    return {
      message: text,
      offerBankTransfer: true,
    }
  }
  return {
    message: text || 'We could not start the payment. Please try again.',
    offerBankTransfer: false,
  }
}

export function invoiceStatus(invoice, today = new Date()) {
  if (!invoice?.due_date) return { key: 'open', label: 'Payment due' }
  const due = new Date(`${invoice.due_date}T23:59:59`)
  return due < today
    ? { key: 'overdue', label: 'Overdue' }
    : { key: 'open', label: 'Payment due' }
}

export function verificationOutcome(result) {
  if (result?.paid)
    return { tone: 'success', text: 'Payment received. Thank you.' }
  if (result?.status && result.status !== 'success') {
    return {
      tone: 'pending',
      text: 'The payment has not completed yet. If you were charged, it will appear shortly.',
    }
  }
  return { tone: 'pending', text: 'We are confirming your payment.' }
}
