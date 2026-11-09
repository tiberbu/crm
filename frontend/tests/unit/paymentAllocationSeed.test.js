import { describe, expect, it } from 'vitest'
import {
  clampInvoiceAllocation,
  resolveMappedInvoicePayment,
} from '../../src/pages/FinanceCockpit/components/crud/paymentAllocationSeed.js'

const paymentDraft = {
  doctype: 'Payment Entry',
  payment_type: 'Receive',
  party_type: 'Customer',
  party: 'CUST-001',
  company: 'Careverse HQ',
  posting_date: '2026-10-12',
  mode_of_payment: 'Cash',
  paid_from_account_currency: 'KES',
  references: [
    {
      reference_doctype: 'Sales Invoice',
      reference_name: 'SINV-001',
      allocated_amount: 1250,
    },
  ],
}

describe('mapped invoice payment context', () => {
  it('retains the mapped company, customer, invoice, currency, and outstanding amount', () => {
    expect(resolveMappedInvoicePayment(paymentDraft, 'Careverse HQ')).toEqual({
      company: 'Careverse HQ',
      customer: 'CUST-001',
      invoice: 'SINV-001',
      amount: 1250,
      currency: 'KES',
      postingDate: '2026-10-12',
      modeOfPayment: 'Cash',
      referenceNo: '',
      referenceDate: '',
    })
  })

  it('rejects a stale company context instead of opening a mismatched payment', () => {
    expect(resolveMappedInvoicePayment(paymentDraft, 'Other Company').error).toMatch(
      /different company/i,
    )
  })

  it('rejects a draft without a valid invoice allocation', () => {
    expect(
      resolveMappedInvoicePayment(
        { ...paymentDraft, references: [] },
        'Careverse HQ',
      ).error,
    ).toMatch(/no Sales Invoice reference/i)
    expect(
      resolveMappedInvoicePayment(
        {
          ...paymentDraft,
          references: [{ ...paymentDraft.references[0], allocated_amount: 0 }],
        },
        'Careverse HQ',
      ).error,
    ).toMatch(/positive outstanding amount/i)
  })

  it('keeps edited allocations partial and bounded by the live outstanding amount', () => {
    expect(clampInvoiceAllocation('500', 1250)).toBe(500)
    expect(clampInvoiceAllocation('1500', 1250)).toBe(1250)
    expect(clampInvoiceAllocation('1250.004', 1250)).toBe(1250)
    expect(clampInvoiceAllocation('-10', 1250)).toBe(0)
  })
})
