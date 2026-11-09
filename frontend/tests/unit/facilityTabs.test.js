import { describe, expect, it } from 'vitest'

import {
  clampPage,
  facilityTabs,
  filterRows,
  pageCount,
  pageOfRow,
  pageSlice,
  rangeText,
  tabIndex,
  tabKey,
} from '@/utils/facilityTabs'

const orders = Array.from({ length: 100 }, (_, i) => ({ name: `SO-${String(i).padStart(3, '0')}` }))

describe('facilityTabs', () => {
  it('starts on Overview and ends on Billing, with Quotes only when shown', () => {
    expect(facilityTabs().map((tab) => tab.key)).toEqual(['overview', 'order', 'invoice', 'payment', 'billing'])
    expect(facilityTabs({ showQuote: true }).map((tab) => tab.label)).toEqual([
      'Overview',
      'Quotes',
      'Orders',
      'Invoices',
      'Payments',
      'Billing',
    ])
  })

  it('carries counts and the invoices-due badge', () => {
    const tabs = facilityTabs({ counts: { order: 12, invoice: 100, invoiceDue: 2, payment: 0 } })
    const byKey = Object.fromEntries(tabs.map((tab) => [tab.key, tab]))
    expect(byKey.order.count).toBe(12)
    expect(byKey.invoice).toMatchObject({ count: 100, due: 2 })
    expect(byKey.payment.count).toBe(0)
    expect(byKey.overview.count).toBeNull()
  })

  it('maps keys to frappe-ui index-based tabs and back', () => {
    const tabs = facilityTabs({ showQuote: true })
    expect(tabIndex(tabs, 'invoice')).toBe(3)
    expect(tabKey(tabs, 3)).toBe('invoice')
    expect(tabIndex(tabs, 'missing')).toBe(0)
    expect(tabKey(tabs, 99)).toBe('overview')
    // Quotes hidden: the same key lands on a different index.
    expect(tabIndex(facilityTabs(), 'invoice')).toBe(2)
  })
})

describe('local paging', () => {
  it('slices 20 rows per page and clamps out-of-range pages', () => {
    expect(pageCount(100)).toBe(5)
    expect(pageCount(0)).toBe(1)
    expect(pageSlice(orders, 0)).toHaveLength(20)
    expect(pageSlice(orders, 4).at(-1).name).toBe('SO-099')
    expect(clampPage(9, 100)).toBe(4)
    expect(pageSlice(orders, 9)[0].name).toBe('SO-080')
  })

  it('finds the page holding a row for cross-links', () => {
    expect(pageOfRow(orders, 'SO-045')).toBe(2)
    expect(pageOfRow(orders, 'SO-999')).toBe(-1)
  })

  it('describes the visible range', () => {
    expect(rangeText(0, 100)).toBe('Showing 1–20 of 100')
    expect(rangeText(4, 95)).toBe('Showing 81–95 of 95')
    expect(rangeText(0, 0)).toBe('No records')
  })
})

describe('filterRows', () => {
  const invoices = [
    { name: 'SINV-1', amount: 10, sales_orders: ['SO-7'] },
    { name: 'SINV-2', amount: 0 },
    { name: 'SINV-3', amount: 5 },
  ]

  it('keeps only outstanding invoices when asked', () => {
    expect(filterRows(invoices, { kind: 'invoice', status: 'outstanding' }).map((row) => row.name)).toEqual([
      'SINV-1',
      'SINV-3',
    ])
    expect(filterRows(invoices, { kind: 'invoice', status: 'all' })).toHaveLength(3)
  })

  it('searches names and linked documents case-insensitively', () => {
    expect(filterRows(invoices, { kind: 'invoice', search: 'so-7' }).map((row) => row.name)).toEqual(['SINV-1'])
    expect(filterRows(orders, { kind: 'order', search: 'so-09' })).toHaveLength(10)
  })
})
