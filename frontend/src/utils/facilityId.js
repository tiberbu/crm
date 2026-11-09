// The Health Facility Registry ID (FID), shown as "Facility ID" wherever an MFL code is shown.
// Older records may carry it as `facility_fid` or `fid`; an MFL code is never used in its place.
export function facilityId(facility) {
  const candidates = [facility?.hfr_facility_id, facility?.facility_fid, facility?.fid, facility?.facility_id]
  return candidates.map((value) => String(value || '').trim()).find((value) => /^FID-/i.test(value)) || ''
}

export function isValidFacilityId(value) {
  return /^FID-\d{2}-[\w-]+$/i.test(String(value || '').trim())
}

// Selected, not-yet-quoted facilities that still have no Facility ID.
export function facilitiesNeedingId(facilities, selectedCodes) {
  const codes = new Set(selectedCodes || [])
  return (facilities || []).filter(
    (facility) => codes.has(facility.mfl_code) && !facility.already_quoted && !facilityId(facility),
  )
}
