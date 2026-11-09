import { describe, expect, it } from 'vitest'
import { PERIOD_MONTHS, gridColumns, periodLabel } from '@/utils/valueExpress'

describe('gridColumns', () => {
  it('keeps up to four cards on one row', () => {
    expect([0, 1, 2, 3, 4].map((n) => gridColumns(n))).toEqual([1, 1, 2, 3, 4])
  })

  it('balances the rows once there are more cards than fit', () => {
    expect([5, 6, 7, 8, 9, 10].map((n) => gridColumns(n))).toEqual([
      3, 3, 4, 4, 3, 4,
    ])
  })

  it('honours a smaller maximum for the Fixed tiers', () => {
    expect([2, 3, 4, 5].map((n) => gridColumns(n, 3))).toEqual([2, 3, 2, 3])
  })
})

describe('periodLabel', () => {
  it('names each billing period', () => {
    expect(Object.keys(PERIOD_MONTHS).map(periodLabel)).toEqual([
      'per month',
      'per quarter',
      'per half-year',
      'per year',
    ])
  })

  it('reads monthly for an unknown period', () => {
    expect(periodLabel('')).toBe('per month')
  })
})
