import { describe, expect, it } from 'vitest'
import {
  checkSummary,
  formatShare,
  formatTokens,
  parseIsoDate,
  showsUsageTab,
  usageDownloadUrl,
  usageRangeError,
  usageRangePresets,
} from '@/utils/usageReport'
import { facilityTabs } from '@/utils/facilityTabs'

const TODAY = new Date(2026, 10, 11) // 11 Nov 2026

describe('usage report range presets', () => {
  it('covers the last 7 and 30 days including today', () => {
    const presets = Object.fromEntries(
      usageRangePresets(TODAY).map((p) => [p.key, p]),
    )
    expect(presets.last7).toMatchObject({
      from: '2026-11-05',
      to: '2026-11-11',
    })
    expect(presets.last30).toMatchObject({
      from: '2026-10-13',
      to: '2026-11-11',
    })
    expect(presets.thisMonth).toMatchObject({
      from: '2026-11-01',
      to: '2026-11-11',
    })
    expect(presets.lastMonth).toMatchObject({
      from: '2026-10-01',
      to: '2026-10-31',
    })
  })

  it('last month crosses a year boundary in January', () => {
    const last = usageRangePresets(new Date(2027, 0, 15)).find(
      (p) => p.key === 'lastMonth',
    )
    expect(last).toMatchObject({ from: '2026-12-01', to: '2026-12-31' })
  })
})

describe('usage report range validation', () => {
  it('accepts a valid range', () => {
    expect(usageRangeError('2026-11-01', '2026-11-11', TODAY)).toBe('')
    expect(usageRangeError('2026-11-11', '2026-11-11', TODAY)).toBe('')
  })

  it('rejects missing, impossible, reversed, future and over-long ranges', () => {
    expect(usageRangeError('', '2026-11-11', TODAY)).toMatch(/start and end/)
    expect(usageRangeError('2026-02-30', '2026-03-01', TODAY)).toMatch(
      /start and end/,
    )
    expect(usageRangeError('2026-11-10', '2026-11-01', TODAY)).toMatch(
      /on or after/,
    )
    expect(usageRangeError('2026-11-12', '2026-11-20', TODAY)).toMatch(/future/)
    expect(usageRangeError('2025-11-01', '2026-11-11', TODAY)).toMatch(
      /at most 366/,
    )
  })

  it('parses only real calendar dates', () => {
    expect(parseIsoDate('2026-11-11')).toBeInstanceOf(Date)
    expect(parseIsoDate('11/11/2026')).toBeNull()
  })
})

describe('usage tab', () => {
  it('shows for token plans with an FID only', () => {
    expect(showsUsageTab({ tokens: true, fid: 'FID-00-AB-1' })).toBe(true)
    expect(showsUsageTab({ tokens: true, fid: '' })).toBe(false)
    expect(showsUsageTab({ tokens: false, fid: 'FID-00-AB-1' })).toBe(false)
  })

  it('sits right after Overview when shown', () => {
    expect(
      facilityTabs({ showUsage: true })
        .map((t) => t.key)
        .slice(0, 2),
    ).toEqual(['overview', 'usage'])
    expect(facilityTabs().map((t) => t.key)).not.toContain('usage')
  })
})

describe('usage formatting', () => {
  it('formats tokens, shares and price checks', () => {
    expect(formatTokens(1234.5)).toBe('1,234.5')
    expect(formatTokens(null)).toBe('—')
    expect(formatShare(0.6923)).toBe('69.2%')
    expect(
      checkSummary({ matches: 9, price_differs: 1, charge_differs: 0 }).map(
        (c) => c.key,
      ),
    ).toEqual(['price_differs', 'matches'])
  })

  it('builds an encoded download URL', () => {
    expect(usageDownloadUrl('12 34', '2026-11-01', '2026-11-11')).toBe(
      '/api/method/crm.api.usage_report.download_facility_usage_report?mfl_code=12+34&from_date=2026-11-01&to_date=2026-11-11',
    )
  })
})
