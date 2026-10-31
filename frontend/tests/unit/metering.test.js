import { describe, expect, it } from 'vitest'
import {
  balanceStats,
  keyState,
  maskedKey,
  probeOutcome,
  tone,
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
