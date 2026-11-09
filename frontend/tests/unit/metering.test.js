import { describe, expect, it } from 'vitest'
import {
  balanceStats,
  keyState,
  maskedKey,
  planSummary,
  probeOutcome,
  tokenLines,
  tone,
  welcomeBonusVia,
} from '@/utils/metering'

describe('keyState', () => {
  it('offers nothing before a key exists', () => {
    expect(keyState({}, true)).toBe('none')
    expect(keyState(null, true)).toBe('none')
  })
  it('reveals only for the Administrator and only stored keys', () => {
    expect(
      keyState(
        { site_key_prefix: 'omk2.FID-1.ab', key_revealable: true },
        true,
      ),
    ).toBe('revealable')
    expect(
      keyState(
        { site_key_prefix: 'omk2.FID-1.ab', key_revealable: false },
        true,
      ),
    ).toBe('legacy')
    expect(
      keyState(
        { site_key_prefix: 'omk2.FID-1.ab', key_revealable: true },
        false,
      ),
    ).toBe('masked')
  })
})

describe('maskedKey', () => {
  it('never shows more than the prefix', () => {
    expect(maskedKey('omk2.FID-1.ab')).toBe('omk2.FID-1.ab…••••••••••••••••')
    expect(maskedKey('')).toBe('')
  })
})

describe('tone', () => {
  it('maps known states and falls back to orange or gray', () => {
    expect(tone('status', 'Active')).toBe('green')
    expect(tone('sync', 'Error')).toBe('red')
    expect(tone('connection', 'Reachable')).toBe('green')
    expect(tone('status', 'Draft')).toBe('orange')
    expect(tone('sync', undefined)).toBe('gray')
  })
})

describe('balanceStats', () => {
  it('shows OpenMeter values and keeps zero as zero', () => {
    const stats = balanceStats({
      granted_total: 100,
      grants: [{ status: 'Granted' }, { status: 'Failed' }],
      entitlement: { usage: 0, balance: 100, overage: 0 },
      site: { token_quantity: 100, usage_period_interval: 'MONTH' },
    })
    expect(stats.map((s) => s.value)).toEqual([100, 0, 100, 0])
    expect(stats[0].hint).toBe('1 grant(s)')
  })
  it('leaves balances empty without an entitlement', () => {
    expect(
      balanceStats({ granted_total: 5, grants: [], site: {} })
        .slice(1)
        .map((s) => s.value),
    ).toEqual([null, null, null])
  })
})

describe('welcomeBonusVia', () => {
  it('is null until the bonus is dispensed', () => {
    expect(welcomeBonusVia({ dispensed: false })).toBeNull()
    expect(welcomeBonusVia(null)).toBeNull()
  })
  it('links the order that auto-selected the bonus', () => {
    expect(
      welcomeBonusVia({
        dispensed: true,
        source_doctype: 'Sales Order',
        source_name: 'SAL-001',
      }),
    ).toEqual({ kind: 'order', name: 'SAL-001' })
  })
  it('links the paid invoice the bonus rode on', () => {
    expect(
      welcomeBonusVia({
        dispensed: true,
        source_doctype: 'Sales Invoice',
        source_name: 'INV-001',
      }),
    ).toEqual({ kind: 'invoice', name: 'INV-001' })
  })
  it('shows the user by full-name label, falling back to the username', () => {
    expect(
      welcomeBonusVia({
        dispensed: true,
        source_doctype: 'User',
        source_name: 'a@b.co',
        source_label: 'A Person',
      }),
    ).toEqual({ kind: 'user', label: 'A Person' })
    expect(
      welcomeBonusVia({
        dispensed: true,
        source_doctype: 'User',
        source_name: 'a@b.co',
      }),
    ).toEqual({ kind: 'user', label: 'a@b.co' })
  })
})

describe('tokenLines', () => {
  const grants = [
    { name: 'welcome:F1', grant_source: 'Welcome Bonus', amount: 400 },
    { name: 'invoice:INV-1', grant_source: 'Token Purchase', amount: 12000 },
    { name: 'purchase:key', grant_source: 'Token Purchase', amount: 3000 },
    { name: 'coupon:F1', grant_source: 'Partner Coupon', amount: 500 },
    { name: 'initial:F1', grant_source: 'Initial Package', amount: 0 },
    { name: 'reissue:F1', grant_source: 'Reissue', amount: 100 },
  ]
  it('separates purchase and coupon lines, one per grant, and keeps the rest out', () => {
    const lines = tokenLines(grants)
    expect(lines.purchase.map((g) => g.name)).toEqual([
      'invoice:INV-1',
      'purchase:key',
    ])
    expect(lines.coupon.map((g) => g.name)).toEqual(['coupon:F1'])
  })
  it('handles empty or missing grants', () => {
    expect(tokenLines([])).toEqual({ purchase: [], coupon: [] })
    expect(tokenLines(undefined)).toEqual({ purchase: [], coupon: [] })
  })
})

describe('probeOutcome', () => {
  it('reports a delivered probe by event', () => {
    expect(
      probeOutcome({ event: { status: 'Delivered', name: 'E1' } }),
    ).toEqual({ delivered: true, event: 'E1' })
  })
  it('explains why a probe was not delivered', () => {
    expect(
      probeOutcome({ event: { status: 'Failed', last_error: '401' } }).message,
    ).toBe('401')
    expect(
      probeOutcome({ event: {}, delivery: { skipped: 'disabled' } }).message,
    ).toBe('disabled')
    expect(probeOutcome({}).delivered).toBe(false)
  })
})

describe('planSummary', () => {
  it('labels a live subscription and allows cancelling it', () => {
    const plan = {
      plan_type: 'subscription',
      subscription: { status: 'active', expires_at: '2026-12-09T00:00:00Z' },
      terms: [{ name: 'subscription:SINV-1' }],
    }
    const summary = planSummary(plan, 'Active')
    expect(summary.label).toBe('Subscription (Fixed)')
    expect(summary.subscriptionTone).toBe('green')
    expect(summary.canCancel).toBe(true)
    expect(summary.canSuspend).toBe(true)
    expect(summary.canReactivate).toBe(false)
    expect(summary.terms).toHaveLength(1)
  })
  it('does not offer cancelling a lapsed or cancelled subscription', () => {
    for (const status of ['expired', 'cancelled']) {
      const summary = planSummary({ plan_type: 'subscription', subscription: { status } }, 'Active')
      expect(summary.canCancel).toBe(false)
    }
    expect(planSummary({ plan_type: 'subscription', subscription: { status: 'scheduled' } }).canCancel).toBe(true)
  })
  it('labels tokens and no plan, and offers reactivating a suspended site', () => {
    expect(planSummary({ plan_type: 'tokens' }, 'Active').label).toBe('Tokens (Flex)')
    const none = planSummary(null, 'Suspended')
    expect(none.label).toBe('No plan yet')
    expect(none.subscription).toBe(null)
    expect(none.canReactivate).toBe(true)
    expect(none.canSuspend).toBe(false)
  })
})
