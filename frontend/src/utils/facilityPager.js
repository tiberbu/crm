// Client-side search and paging for the onboarding facility list. The verified session returns
// every facility at once; paging only limits how many cards are on screen.
export const FACILITY_PAGE_SIZE = 10

export function filterFacilities(facilities, query) {
  const needle = String(query || '').trim().toLowerCase()
  if (!needle) return facilities || []
  return (facilities || []).filter((facility) =>
    [facility.facility_name, facility.mfl_code].some((value) =>
      String(value || '').toLowerCase().includes(needle),
    ),
  )
}

// Clamps the page, so a search that shrinks the list never leaves an empty page.
export function facilityPage(facilities, page, size = FACILITY_PAGE_SIZE) {
  const total = (facilities || []).length
  const pages = Math.max(1, Math.ceil(total / size))
  const current = Math.min(Math.max(Number(page) || 1, 1), pages)
  const start = (current - 1) * size
  return {
    items: (facilities || []).slice(start, start + size),
    page: current,
    pages,
    total,
    from: total ? start + 1 : 0,
    to: Math.min(start + size, total),
  }
}
