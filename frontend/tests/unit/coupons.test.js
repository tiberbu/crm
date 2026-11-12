import { describe, expect, it } from 'vitest'
import {
  cleanLevelRewards,
  couponLevelLines,
  couponMatches,
  couponOfferByLevel,
  couponValueLabel,
  derivedStatus,
  parseMflList,
  partnerCouponLink,
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
  it('is Inactive ahead of the date window', () => {
    expect(
      derivedStatus({ status: 'Inactive', valid_from: '2999-01-01' }),
    ).toBe('Inactive')
  })
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

describe('couponMatches', () => {
  const coupon = {
    network: 'north-net',
    network_name: 'Northern Partner Network',
    coupon_title: 'Launch bonus',
    coupon_code: 'LAUNCH-24',
  }
  it('matches the partner network name case-insensitively', () => {
    expect(couponMatches(coupon, 'northern partner')).toBe(true)
  })
  it('matches the network ID, title and code', () => {
    expect(couponMatches(coupon, 'north-net')).toBe(true)
    expect(couponMatches(coupon, 'launch b')).toBe(true)
    expect(couponMatches(coupon, 'launch-24')).toBe(true)
  })
  it('matches everything on an empty query', () => {
    expect(couponMatches(coupon, '  ')).toBe(true)
  })
  it('rejects a non-matching query', () => {
    expect(couponMatches(coupon, 'southern')).toBe(false)
  })
})

describe('couponValueLabel by plan (P-108)', () => {
  it('reads a Fixed coupon as a discount', () => {
    expect(
      couponValueLabel({ applies_to: 'Fixed', fixed_discount_percent: 5 }),
    ).toBe('5% off Fixed')
  })
  it('reads a Both coupon as tokens on Flex and a discount on Fixed', () => {
    expect(
      couponValueLabel({
        applies_to: 'Both',
        value_type: 'flat_tokens',
        value: 1000,
        fixed_discount_percent: 7.5,
      }),
    ).toBe('1,000 tokens on Flex · 7.5% off Fixed')
  })
  it('keeps Flex and plan-less coupons as their token value', () => {
    expect(
      couponValueLabel({ applies_to: 'Flex', value_type: 'flat_tokens', value: 500 }),
    ).toBe('500 tokens')
    expect(couponValueLabel({ value_type: 'flat_tokens', value: 500 })).toBe(
      '500 tokens',
    )
  })
})

describe('coupon rewards by facility level (P-116 to P-123)', () => {
  const both = {
    applies_to: 'Both',
    value_type: 'flat_tokens',
    value: 0,
    fixed_discount_percent: 0,
    reward_by_level: 1,
    level_rewards: [
      { facility_level: 'Level 2', flex_value: 1000, fixed_discount_percent: 10 },
      { facility_level: 'Level 4', flex_value: 2500, fixed_discount_percent: 0 },
    ],
  }
  it('labels a level-rewarded coupon "By facility level"', () => {
    expect(couponValueLabel(both)).toBe('By facility level')
  })
  it('lists each level, then all other levels', () => {
    expect(couponLevelLines(both)).toEqual([
      { level: 'Level 2', label: '1,000 tokens on Flex · 10% off Fixed' },
      { level: 'Level 4', label: '2,500 tokens' },
      { level: 'All other levels', label: 'No reward' },
    ])
  })
  it('uses the coupon value type and cap for every level', () => {
    const pct = {
      applies_to: 'Flex',
      value_type: 'percentage_of_purchase',
      value: 5,
      max_tokens: 400,
      reward_by_level: 1,
      level_rewards: [{ facility_level: 'Level 3B', flex_value: 20 }],
    }
    expect(couponLevelLines(pct)).toEqual([
      { level: 'Level 3B', label: '20% of purchase (max 400)' },
      { level: 'All other levels', label: '5% of purchase (max 400)' },
    ])
  })
  it('has no level lines when levels are off', () => {
    expect(couponLevelLines({ ...both, reward_by_level: 0 })).toEqual([])
  })
  it('reads the guest offer per level, leaving out levels that get nothing', () => {
    expect(couponOfferByLevel(both)).toBe(
      'Level 2: +1,000 tokens on Flex · 10% off Fixed; Level 4: +2,500 tokens',
    )
    const fixed = {
      applies_to: 'Fixed',
      fixed_discount_percent: 3,
      reward_by_level: 1,
      level_rewards: [{ facility_level: 'Level 2', fixed_discount_percent: 8 }],
    }
    expect(couponOfferByLevel(fixed)).toBe(
      'Level 2: 8% off Fixed; All other levels: 3% off Fixed',
    )
  })
  it('cleans the rows the dialog sends', () => {
    expect(
      cleanLevelRewards([
        { facility_level: '  Level   3B ', flex_value: '500', fixed_discount_percent: '' },
        { facility_level: '', flex_value: 0, fixed_discount_percent: 0 },
      ]),
    ).toEqual([{ facility_level: 'Level 3B', flex_value: 500, fixed_discount_percent: 0 }])
  })
})

describe('partnerCouponLink', () => {
  it('builds a full link on the site base URL', () => {
    expect(partnerCouponLink('https://site.example.test', '123456')).toBe(
      'https://site.example.test/facility-onboarding?partner_coupon=123456',
    )
  })
  it('drops trailing slashes on the base and encodes the coupon', () => {
    expect(partnerCouponLink('https://site.example.test//', ' 12 34 ')).toBe(
      'https://site.example.test/facility-onboarding?partner_coupon=12%2034',
    )
  })
  it('returns an empty string without a coupon', () => {
    expect(partnerCouponLink('https://site.example.test', '')).toBe('')
    expect(partnerCouponLink('https://site.example.test', null)).toBe('')
  })
})
