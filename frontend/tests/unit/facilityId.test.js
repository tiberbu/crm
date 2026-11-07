import { describe, expect, it } from 'vitest'
import { facilityId, facilitiesNeedingId, isValidFacilityId } from '@/utils/facilityId'

describe('isValidFacilityId', () => {
  it('accepts the HFR format', () => {
    expect(isValidFacilityId('FID-00-12345-1')).toBe(true)
    expect(isValidFacilityId('fid-99-abc')).toBe(true)
    expect(isValidFacilityId('  FID-00-abc  ')).toBe(true)
  })

  it('rejects malformed values', () => {
    expect(isValidFacilityId('FID-1')).toBe(false)
    expect(isValidFacilityId('FID-AB-1')).toBe(false)
    expect(isValidFacilityId('MFL-12345')).toBe(false)
    expect(isValidFacilityId('')).toBe(false)
    expect(isValidFacilityId(undefined)).toBe(false)
  })
})

describe('facilitiesNeedingId', () => {
  const facilities = [
    { mfl_code: 'MFL-1', facility_name: 'One', already_quoted: false, hfr_facility_id: '' },
    { mfl_code: 'MFL-2', facility_name: 'Two', already_quoted: false, hfr_facility_id: 'FID-00-TWO' },
    { mfl_code: 'MFL-3', facility_name: 'Three', already_quoted: true, hfr_facility_id: '' },
    { mfl_code: 'MFL-4', facility_name: 'Four', already_quoted: false, fid: 'FID-00-FOUR' },
  ]

  it('returns only selected, not-quoted rows without an ID', () => {
    const need = facilitiesNeedingId(facilities, ['MFL-1', 'MFL-2', 'MFL-3', 'MFL-4'])
    expect(need.map((f) => f.mfl_code)).toEqual(['MFL-1'])
  })

  it('ignores unselected facilities', () => {
    expect(facilitiesNeedingId(facilities, [])).toEqual([])
  })

  it('never offers already-quoted facilities', () => {
    expect(facilitiesNeedingId(facilities, ['MFL-3'])).toEqual([])
  })
})

describe('facilityId', () => {
  it('reads the registered field first and never an MFL', () => {
    expect(facilityId({ hfr_facility_id: 'FID-00-A' })).toBe('FID-00-A')
    expect(facilityId({ fid: 'FID-00-B' })).toBe('FID-00-B')
    expect(facilityId({ mfl_code: 'MFL-1' })).toBe('')
  })
})
