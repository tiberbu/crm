import { describe, expect, it } from 'vitest'
import {
  couponValueLabel,
  derivedStatus,
  parseMflList,
  VALUE_TYPES,
} from '@/utils/coupons'

describe('couponValueLabel', () => {
  it('labels flat tokens with grouping', () => {
    expect(couponValueLabel({ value_type: 'flat_tokens', value: 1000 })).toBe(
      '1,000 tokens',
    )
    expect(couponValueLabel({ value_type: 'flat_tokens', value: 50 })).toBe(
      '50 tokens',
    )
  })

  it('labels a percentage of purchase', () => {
    expect(
      couponValueLabel({ value_type: 'percentage_of_purchase', value: 5 }),
    ).toBe('5% of purchase')
  })

  it('adds the cap when present', () => {
    expect(
      couponValueLabel({
        value_type: 'percentage_of_purchase',
        value: 5,
        max_tokens: 500,
      }),
    ).toBe('5% of purchase (max 500)')
    expect(
      couponValueLabel({
        value_type: 'flat_tokens',
        value: 100,
        max_tokens: 0,
      }),
    ).toBe('100 tokens')
  })
})

describe('derivedStatus', () => {
  const base = {
    status: 'Active',
    valid_from: null,
    valid_to: null,
    max_redemptions: 0,
    redeemed_count: 0,
  }
  it('prefers Revoked', () => {
    expect(derivedStatus({ ...base, status: 'Revoked' })).toBe('Revoked')
  })
  it('is Exhausted at the limit', () => {
    expect(
      derivedStatus({ ...base, max_redemptions: 5, redeemed_count: 5 }),
    ).toBe('Exhausted')
  })
  it('is unlimited when max is 0', () => {
    expect(
      derivedStatus({ ...base, max_redemptions: 0, redeemed_count: 999 }),
    ).toBe('Active')
  })
})

describe('parseMflList', () => {
  it('splits commas and newlines, trims, de-dupes', () => {
    expect(parseMflList('90011, 90012\n90013, 90011')).toEqual([
      '90011',
      '90012',
      '90013',
    ])
  })
  it('drops empty entries', () => {
    expect(parseMflList('  ,, ')).toEqual([])
  })
})

describe('VALUE_TYPES', () => {
  it('has both value types', () => {
    expect(Object.keys(VALUE_TYPES)).toEqual([
      'flat_tokens',
      'percentage_of_purchase',
    ])
  })
})
