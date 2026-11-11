// Facility usage report on the CX Portal (P-135, docs/cx-facility-usage-report.md).
// Pure helpers: date-range presets and validation, labels and the download URL.

export const MAX_RANGE_DAYS = 366

export const CHECKS = {
  matches: { label: 'Matches the price', tone: 'success' },
  price_differs: { label: 'Price differs from current list', tone: 'warning' },
  charge_differs: {
    label: 'Charge differs from quantity × price',
    tone: 'error',
  },
  pre_priced: { label: 'Pre-priced (ledger export)', tone: 'neutral' },
}

export const SOURCES = {
  paid: 'Paid tokens',
  package: 'Initial package',
  bonus: 'Welcome bonus',
  coupon: 'Coupon',
  other: 'Other',
}

function pad(n) {
  return String(n).padStart(2, '0')
}

export function isoDate(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function parseIsoDate(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || ''))
  if (!match) return null
  const date = new Date(
    Number(match[1]),
    Number(match[2]) - 1,
    Number(match[3]),
  )
  return isoDate(date) === value ? date : null
}

function addDays(date, days) {
  const next = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  next.setDate(next.getDate() + days)
  return next
}

// Presets offered above the custom From/To fields; `today` is a Date (local).
export function usageRangePresets(today = new Date()) {
  const day = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  const monthStart = new Date(day.getFullYear(), day.getMonth(), 1)
  const lastMonthEnd = addDays(monthStart, -1)
  const lastMonthStart = new Date(
    lastMonthEnd.getFullYear(),
    lastMonthEnd.getMonth(),
    1,
  )
  return [
    {
      key: 'last7',
      label: 'Last 7 days',
      from: isoDate(addDays(day, -6)),
      to: isoDate(day),
    },
    {
      key: 'last30',
      label: 'Last 30 days',
      from: isoDate(addDays(day, -29)),
      to: isoDate(day),
    },
    {
      key: 'thisMonth',
      label: 'This month',
      from: isoDate(monthStart),
      to: isoDate(day),
    },
    {
      key: 'lastMonth',
      label: 'Last month',
      from: isoDate(lastMonthStart),
      to: isoDate(lastMonthEnd),
    },
  ]
}

// '' when the range is usable, else the message to show beside the fields.
export function usageRangeError(from, to, today = new Date()) {
  const start = parseIsoDate(from)
  const end = parseIsoDate(to)
  if (!start || !end) return 'Choose a start and end date.'
  if (end < start) return 'The end date must be on or after the start date.'
  const day = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  if (start > day) return 'The start date cannot be in the future.'
  const days = Math.round((end - start) / 86400000) + 1
  if (days > MAX_RANGE_DAYS)
    return `Choose a range of at most ${MAX_RANGE_DAYS} days.`
  return ''
}

// Token plans (Flex or metered) with an HFR Facility ID get the Usage tab.
export function showsUsageTab({ tokens, fid }) {
  return Boolean(tokens) && /^FID-/i.test(String(fid || '').trim())
}

export function formatTokens(value) {
  if (value === null || value === undefined || value === '') return '—'
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  return number.toLocaleString('en-KE', { maximumFractionDigits: 2 })
}

export function formatShare(share) {
  const number = Number(share) || 0
  return `${(number * 100).toLocaleString('en-KE', { maximumFractionDigits: 1 })}%`
}

export function checkLabel(key) {
  return CHECKS[key]?.label || key || '—'
}

export function checkTone(key) {
  return CHECKS[key]?.tone || 'neutral'
}

// Price-check counts in a fixed order, problems first; zero counts dropped.
export function checkSummary(checks = {}) {
  return ['charge_differs', 'price_differs', 'pre_priced', 'matches']
    .filter((key) => Number(checks?.[key]) > 0)
    .map((key) => ({
      key,
      label: CHECKS[key].label,
      tone: CHECKS[key].tone,
      count: Number(checks[key]),
    }))
}

export function usageDownloadUrl(mflCode, from, to) {
  const params = new URLSearchParams({
    mfl_code: mflCode || '',
    from_date: from || '',
    to_date: to || '',
  })
  return `/api/method/crm.api.usage_report.download_facility_usage_report?${params.toString()}`
}
