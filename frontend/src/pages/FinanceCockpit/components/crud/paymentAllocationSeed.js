/** Validate the context returned by the invoice-to-payment mapper. */
export function resolveMappedInvoicePayment(seed, activeCompany) {
  if (!seed || seed.doctype !== 'Payment Entry') {
    return { error: 'The mapped payment draft is unavailable. Please prepare it again.' }
  }
  if (seed.payment_type !== 'Receive' || seed.party_type !== 'Customer' || !seed.party) {
    return { error: 'This draft is not a customer receipt. Please prepare the payment again.' }
  }
  if (!seed.company || seed.company !== activeCompany) {
    return {
      error: 'The invoice belongs to a different company than the active Finance workspace. Switch companies and prepare the payment again.',
    }
  }

  const reference = (Array.isArray(seed.references) ? seed.references : []).find(
    (row) => row.reference_doctype === 'Sales Invoice' && row.reference_name,
  )
  if (!reference) {
    return { error: 'The mapped payment has no Sales Invoice reference. Please prepare it again.' }
  }

  const amount = Number(reference.allocated_amount)
  if (!Number.isFinite(amount) || amount <= 0) {
    return { error: 'The invoice has no positive outstanding amount. Refresh the invoice and try again.' }
  }

  return {
    company: seed.company,
    customer: seed.party,
    invoice: reference.reference_name,
    amount,
    currency: seed.paid_from_account_currency || seed.paid_to_account_currency || '',
    postingDate: seed.posting_date || '',
    modeOfPayment: seed.mode_of_payment || '',
    referenceNo: seed.reference_no || '',
    referenceDate: seed.reference_date || '',
  }
}

/** Keep an editable allocation between zero and the invoice's live balance. */
export function clampInvoiceAllocation(rawAmount, outstandingAmount) {
  const amount = Number.parseFloat(rawAmount)
  const outstanding = Number(outstandingAmount)
  if (!Number.isFinite(amount) || !Number.isFinite(outstanding)) return 0
  return Math.min(Math.max(amount, 0), outstanding)
}
