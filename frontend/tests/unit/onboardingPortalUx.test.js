import { describe, expect, it } from 'vitest'

import { facilityPage, filterFacilities } from '@/utils/facilityPager'
import { partnerName, pricePerToken } from '@/utils/portalPartner'
import { termsDocument, termsFileName } from '@/utils/termsDownload'

const facilities = Array.from({ length: 25 }, (_, index) => ({
  facility_name: `Clinic ${index + 1}`,
  mfl_code: `M-${index + 1}`,
}))

describe('facility pager', () => {
  it('shows ten facilities per page and clamps the page', () => {
    expect(facilityPage(facilities, 1)).toMatchObject({ page: 1, pages: 3, total: 25, from: 1, to: 10 })
    expect(facilityPage(facilities, 3)).toMatchObject({ from: 21, to: 25 })
    expect(facilityPage(facilities, 3).items).toHaveLength(5)
    expect(facilityPage(facilities, 9).page).toBe(3)
    expect(facilityPage([], 2)).toMatchObject({ page: 1, pages: 1, from: 0, to: 0 })
  })

  it('searches by name or MFL code', () => {
    expect(filterFacilities(facilities, 'clinic 2').map((f) => f.mfl_code)).toEqual([
      'M-2', 'M-20', 'M-21', 'M-22', 'M-23', 'M-24', 'M-25',
    ])
    expect(filterFacilities(facilities, ' m-7 ')).toHaveLength(1)
    expect(filterFacilities(facilities, '')).toBe(facilities)
  })
})

describe('partnerName', () => {
  it('hides the no-network record', () => {
    expect(partnerName('No Network')).toBe('')
    expect(partnerName('no-network')).toBe('')
    expect(partnerName('')).toBe('')
    expect(partnerName(null)).toBe('')
    expect(partnerName(' Example Partner ')).toBe('Example Partner')
  })
})

describe('pricePerToken', () => {
  it('divides the price excl. VAT by the tokens', () => {
    expect(pricePerToken({ price_ex_vat: 6000, price: 6960, token_quantity: 1000 })).toBe(6)
    expect(pricePerToken({ price: 0, token_quantity: 100 })).toBeNull()
    expect(pricePerToken({ price: 100, token_quantity: 0 })).toBeNull()
  })
})

describe('terms download', () => {
  const snapshot = {
    document: 'Onboarding <Terms>',
    rendered_html: '<p>Clause one.</p>',
    content_hash: 'abc123',
  }

  it('wraps the accepted Terms with a script-blocking policy and its reference', () => {
    const html = termsDocument(snapshot, '27 Oct 2026')
    expect(html).toContain("Content-Security-Policy\" content=\"default-src 'none'")
    expect(html).toContain('<p>Clause one.</p>')
    expect(html).toContain('Reference: abc123')
    expect(html).toContain('<title>Onboarding &lt;Terms&gt;</title>')
  })

  it('names the file after the document', () => {
    expect(termsFileName('Self Onboarding Terms v2')).toBe('self-onboarding-terms-v2.html')
    expect(termsFileName('')).toBe('terms-and-conditions.html')
  })
})
