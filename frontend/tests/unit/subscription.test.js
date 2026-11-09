import { describe, expect, it } from 'vitest'
import { formatDay, subscriptionCard } from '@/utils/subscription'

const day = (iso) => (iso ? iso.slice(0, 10) : '')

describe('subscriptionCard', () => {
  const base = {
    package: 'Fixed Level 2',
    activated_at: '2026-11-09T10:00:00Z',
    expires_at: '2026-12-09T10:00:00Z',
    cancelled_at: null,
  }
  it('shows an active term with its expiry and start', () => {
    expect(subscriptionCard({ ...base, status: 'active' }, day)).toEqual({
      value: 'Active until 2026-12-09',
      note: 'Active since 2026-11-09 · Fixed Level 2',
    })
  })
  it('shows scheduled, expired and cancelled terms', () => {
    expect(subscriptionCard({ ...base, status: 'scheduled' }, day).value).toBe(
      'Starts 2026-11-09',
    )
    expect(subscriptionCard({ ...base, status: 'expired' }, day).value).toBe(
      'Expired 2026-12-09',
    )
    expect(
      subscriptionCard(
        { ...base, status: 'cancelled', cancelled_at: '2026-11-20T08:00:00Z' },
        day,
      ).value,
    ).toBe('Cancelled 2026-11-20')
  })
  it('is null without a subscription', () => {
    expect(subscriptionCard(null)).toBe(null)
    expect(subscriptionCard({})).toBe(null)
  })
  it('formats ISO days and tolerates bad input', () => {
    expect(formatDay('2026-12-09T10:00:00Z')).toMatch(/2026/)
    expect(formatDay('not a date')).toBe('')
    expect(formatDay(null)).toBe('')
  })
})
