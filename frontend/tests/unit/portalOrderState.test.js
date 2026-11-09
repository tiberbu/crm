import { describe, expect, it } from 'vitest'
import {
  facilityLabel,
  findOpenOrder,
  invoiceStatus,
  oisForReference,
  packageLabel,
  paymentFailureMessage,
  referenceFromSearch,
  verificationOutcome,
} from '@/utils/portalOrderState'

const orders = [
  {
    name: 'SO-1',
    crm_token_facility_mfl: '90001',
    crm_token_package_item: 'TOK-A',
  },
  {
    name: 'SO-2',
    crm_token_facility_mfl: '90002',
    crm_token_package_item: 'TOK-A',
  },
]

describe('portalOrderState', () => {
  it('finds the open order to resume for a facility and package', () => {
    expect(findOpenOrder(orders, '90002', 'TOK-A')?.name).toBe('SO-2')
    expect(findOpenOrder(orders, 90001, 'TOK-A')?.name).toBe('SO-1')
    expect(findOpenOrder(orders, '90001', 'TOK-B')).toBeNull()
    expect(findOpenOrder(undefined, '1', 'x')).toBeNull()
  })

  it('labels packages and facilities with a safe fallback', () => {
    expect(
      packageLabel('TOK-A', [{ item_code: 'TOK-A', display_name: 'Core' }]),
    ).toBe('Core')
    expect(packageLabel('TOK-Z', [])).toBe('TOK-Z')
    expect(facilityLabel('9', [{ mfl_code: 9, facility_name: 'Alpha' }])).toBe(
      'Alpha',
    )
  })

  it('accepts only a well-formed Paystack reference from the URL', () => {
    expect(
      referenceFromSearch('?reference=OIS-OIS-2026-00001-INV-1-ab12'),
    ).toBe('OIS-OIS-2026-00001-INV-1-ab12')
    expect(referenceFromSearch('?reference=<script>')).toBe('')
    expect(referenceFromSearch('')).toBe('')
  })

  it('maps a reference to one of the user’s own OIS records only', () => {
    const own = ['OIS-2026-00001', 'OIS-2026-00010']
    expect(oisForReference('OIS-OIS-2026-00010-ACC-SINV-1-ff', own)).toBe(
      'OIS-2026-00010',
    )
    expect(oisForReference('OIS-OIS-2026-00099-ACC-SINV-1-ff', own)).toBe('')
  })

  it('offers bank transfer only when Paystack is not configured', () => {
    expect(
      paymentFailureMessage({
        messages: ['Paystack is not configured. Use bank transfer.'],
      }),
    ).toMatchObject({ offerBankTransfer: true })
    expect(paymentFailureMessage({})).toMatchObject({
      offerBankTransfer: false,
    })
  })

  it('flags overdue invoices', () => {
    const today = new Date('2026-10-12T10:00:00')
    expect(invoiceStatus({ due_date: '2026-10-11' }, today).key).toBe('overdue')
    expect(invoiceStatus({ due_date: '2026-10-12' }, today).key).toBe('open')
    expect(invoiceStatus({}, today).label).toBe('Payment due')
  })

  it('describes verification outcomes', () => {
    expect(verificationOutcome({ paid: true }).tone).toBe('success')
    expect(verificationOutcome({ paid: false, status: 'abandoned' }).tone).toBe(
      'pending',
    )
  })
})
