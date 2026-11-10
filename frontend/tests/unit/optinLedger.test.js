import { describe, expect, it } from 'vitest'

import {
  advanceLabels,
  advanceTotal,
  nextScheduledPeriod,
  payableInvoice,
  periodAction,
  periodRange,
  quotationPdfUrl,
  stateTone,
  yearOpenByDefault,
  yearSummary,
} from '@/utils/optinLedger'
import { facilityTabs } from '@/utils/facilityTabs'

const next = [
  { label: 'Year 1 · Q1', amount: 98922.24 },
  { label: 'Year 1 · Q2', amount: 98922.24 },
  { label: 'Year 1 · Q3', amount: 98922.24 },
]

describe('Opt-In ledger display rules', () => {
  it('uses status colours only for states that need or record action', () => {
    expect(stateTone('due')).toBe('warning')
    expect(stateTone('overdue')).toBe('danger')
    expect(stateTone('paid_ahead')).toBe('success')
    expect(stateTone('scheduled')).toBe('neutral')
    expect(stateTone('order_ready')).toBe('neutral')
  })

  it('offers Pay only on an issued, unpaid invoice without a pending report', () => {
    expect(periodAction({ sales_invoice: '', outstanding: 0 })).toBe('')
    expect(periodAction({ sales_invoice: 'SINV-1', outstanding: 10, payments: [] })).toBe('pay')
    expect(periodAction({ sales_invoice: 'SINV-1', outstanding: 0 })).toBe('')
    expect(
      periodAction({ sales_invoice: 'SINV-1', outstanding: 10, payments: [{ status: 'Pending verification' }] }),
    ).toBe('pending')
  })

  it('hands the payment modal the invoice row it expects', () => {
    expect(payableInvoice({ sales_invoice: 'SINV-1', outstanding: 98922, invoice_total: 98922.24, due_date: '2027-03-01' }, 'OIS-1')).toEqual({
      name: 'SINV-1',
      invoice_number: 'SINV-1',
      amount: 98922,
      outstanding_amount: 98922,
      grand_total: 98922.24,
      currency: 'KES',
      due_date: '2027-03-01',
      ois_name: 'OIS-1',
    })
  })

  it('finds the next invoice and totals the due periods', () => {
    const years = [
      { periods: [{ label: 'Year 1 · Q1', sales_invoice: 'S1', amount: 5 }] },
      { periods: [{ label: 'Year 2 · Q1', amount: '7', scheduled_date: '2027-01-30', due_date: '2027-03-01' }] },
    ]
    expect(nextScheduledPeriod(years)).toEqual({
      label: 'Year 2 · Q1',
      amount: 7,
      scheduled_date: '2027-01-30',
      due_date: '2027-03-01',
    })
    expect(nextScheduledPeriod([{ periods: [{ sales_invoice: 'S1' }] }])).toBeNull()
    expect(advanceTotal(next, 2)).toBeCloseTo(197844.48)
    expect(periodRange(advanceLabels(next, 3))).toBe('Year 1 · Q1 – Year 1 · Q3')
    expect(periodRange(advanceLabels(next, 1))).toBe('Year 1 · Q1')
  })

  it('opens the first year and any year that needs action', () => {
    const quiet = { periods: [{ state: 'scheduled' }] }
    expect(yearOpenByDefault(quiet, 0)).toBe(true)
    expect(yearOpenByDefault(quiet, 2)).toBe(false)
    expect(yearOpenByDefault({ periods: [{ state: 'overdue' }] }, 3)).toBe(true)
    expect(yearSummary({ periods: [{ state: 'paid', amount: 1 }, { state: 'due', amount: 2 }] })).toEqual({ paid: 1, count: 2, total: 3 })
  })

  it('builds the permission-checked quote PDF link', () => {
    expect(quotationPdfUrl('SAL-QTN-1', { oisNumber: 'OIS-1' })).toBe(
      '/api/method/crm.api.optin_ledger.quotation_pdf?quotation=SAL-QTN-1&ois_number=OIS-1',
    )
    expect(quotationPdfUrl('SAL-QTN-1', { customer: 'C 1' })).toContain('customer=C+1')
    expect(quotationPdfUrl('')).toBe('')
  })

  it('adds the Payment schedule tab after Overview for Network Opt-In facilities', () => {
    expect(facilityTabs({ showQuote: true, showSchedule: true }).map((tab) => tab.key)).toEqual([
      'overview',
      'schedule',
      'quote',
      'order',
      'invoice',
      'payment',
      'billing',
    ])
    expect(facilityTabs({ showQuote: true }).map((tab) => tab.key)).not.toContain('schedule')
  })
})
