import { describe, expect, it } from 'vitest'
import {
  CUSTOM,
  customQuote,
  fixedForLevel,
  journeys,
  monthOneTokens,
  morePercent,
  parseCarriedChoice,
  perTokenRate,
} from '@/utils/valueExpress'

const FLEX = [
  { item_code: 'STARTER', price_ex_vat: 6000, token_quantity: 1000 },
  { item_code: 'GROWTH', price_ex_vat: 15000, token_quantity: 2800 },
  { item_code: 'SCALE', price_ex_vat: 30000, token_quantity: 6250 },
]
const OFFER = {
  min_tokens: 1000,
  tiers: [
    { name: 'Starter', from_amount: 6000, rate: 6 },
    { name: 'Growth', from_amount: 15000, rate: 5.36 },
    { name: 'Scale', from_amount: 30000, rate: 4.8 },
  ],
}

describe('Value Express pricing helpers', () => {
  it('shows the published per-token rates and the extra tokens', () => {
    expect(FLEX.map(perTokenRate)).toEqual([6, 5.36, 4.8])
    expect(FLEX.map((pkg) => morePercent(pkg, FLEX))).toEqual([0, 12, 25])
    expect([1000, 2800, 6250].map(journeys)).toEqual([25, 70, 156])
  })

  it('prices a Custom amount like the server does', () => {
    expect(customQuote(7000, OFFER)).toMatchObject({ ok: true, tier: 'Starter', tokens: 1166, charge: 6996 })
    expect(customQuote(20000, OFFER)).toMatchObject({ tier: 'Growth', rate: 5.36, tokens: 3731 })
    expect(customQuote('40000', OFFER)).toMatchObject({ tier: 'Scale', tokens: 8333, charge: 39998.4 })
    expect(customQuote(14999.99, OFFER).tier).toBe('Starter')
    expect(customQuote(20000, OFFER).charge).toBeLessThanOrEqual(20000)
  })

  it('refuses Custom amounts below the minimum or without tiers', () => {
    expect(customQuote(5999, OFFER).ok).toBe(false)
    expect(customQuote('abc', OFFER).ok).toBe(false)
    expect(customQuote(7000, null).ok).toBe(false)
  })

  it('matches the Fixed package to the registry level', () => {
    const fixed = [
      { item_code: 'L2', facility_levels: ['Level 2'] },
      { item_code: 'L3', facility_levels: ['Level 3B', 'Level 3C'] },
    ]
    expect(fixedForLevel('Level 2', fixed).item_code).toBe('L2')
    expect(fixedForLevel(' level  3c ', fixed).item_code).toBe('L3')
    expect(fixedForLevel('Level 4', fixed)).toBeNull()
    expect(fixedForLevel('', fixed)).toBeNull()
  })

  it('reads the choice carried from the landing page', () => {
    expect(parseCarriedChoice('?plan=flex&package=CV-TOKEN-GROWTH')).toEqual({ plan: 'flex', package: 'CV-TOKEN-GROWTH', coupon: null })
    expect(parseCarriedChoice('?plan=fixed')).toEqual({ plan: 'fixed', coupon: null })
    expect(parseCarriedChoice('?plan=custom&amount=7000')).toEqual({ plan: 'flex', package: CUSTOM, amount: 7000, coupon: null })
    expect(parseCarriedChoice('?plan=custom&amount=-3').amount).toBeNull()
    expect(parseCarriedChoice('?network=x')).toBeNull()
  })

  it('carries a well-formed Partner Coupon from the URL, alone or with a plan', () => {
    expect(parseCarriedChoice('?partner_coupon=123456')).toEqual({ coupon: '123456' })
    expect(parseCarriedChoice('?partner_id=654321')).toEqual({ coupon: '654321' })
    expect(parseCarriedChoice('?plan=flex&package=CV-TOKEN-GROWTH&partner_coupon=123456')).toEqual({
      plan: 'flex',
      package: 'CV-TOKEN-GROWTH',
      coupon: '123456',
    })
    expect(parseCarriedChoice('?partner_coupon=123456&partner_id=654321').coupon).toBe('123456')
    expect(parseCarriedChoice('?partner_coupon=12345')).toBeNull()
    expect(parseCarriedChoice('?partner_coupon=abcdef')).toBeNull()
    expect(parseCarriedChoice('?partner_coupon=%20123456%20')).toEqual({ coupon: '123456' })
  })

  it('counts month-one service tokens after the access charge', () => {
    expect(monthOneTokens(1000, 400, 500)).toBe(900)
    expect(monthOneTokens(100, 0, 500)).toBe(0)
  })
})
