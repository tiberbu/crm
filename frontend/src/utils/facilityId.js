// The Health Facility Registry ID (FID), shown as "Facility ID" wherever an MFL code is shown.
// Older records may carry it as `facility_fid` or `fid`; an MFL code is never used in its place.
export function facilityId(facility) {
  const candidates = [facility?.hfr_facility_id, facility?.facility_fid, facility?.fid, facility?.facility_id]
  return candidates.map((value) => String(value || '').trim()).find((value) => /^FID-/i.test(value)) || ''
}
