/** Pure helpers for the coupon admin UI. Kept dependency-free so they are unit-tested. */

export const VALUE_TYPES = {
  flat_tokens: 'Flat tokens',
  percentage_of_purchase: '% of purchase',
}

/** Human value: "1,000 tokens" or "5% of purchase" or "5% of purchase (max 500)". */
export function couponValueLabel(coupon) {
  const value = Number(coupon?.value || 0)
  if (coupon?.value_type === 'percentage_of_purchase') {
    let label = `${value}% of purchase`
    const cap = Number(coupon?.max_tokens || 0)
    if (cap > 0) label += ` (max ${cap.toLocaleString()})`
    return label
  }
  return `${value.toLocaleString()} tokens`
}

/** The effective status shown in the list: Revoked > Scheduled > Expired > Exhausted > Active. */
export function derivedStatus(coupon) {
  if (coupon?.status === 'Revoked') return 'Revoked'
  const today = new Date()
  const from = coupon?.valid_from ? new Date(coupon.valid_from) : null
  const to = coupon?.valid_to ? new Date(coupon.valid_to) : null
  if (from && today < from) return 'Scheduled'
  if (to && today > to) return 'Expired'
  const max = Number(coupon?.max_redemptions || 0)
  if (max > 0 && Number(coupon?.redeemed_count || 0) >= max) return 'Exhausted'
  return 'Active'
}

export const COUPON_STATUS_THEME = {
  Active: 'green',
  Revoked: 'red',
  Scheduled: 'blue',
  Expired: 'orange',
  Exhausted: 'gray',
}

/** Split free-text (comma- or newline-separated) into trimmed, unique, non-empty MFL codes. */
export function parseMflList(text) {
  const seen = new Set()
  const out = []
  for (const part of String(text || '').replace(/\n/g, ',').split(',')) {
    const mfl = part.trim()
    if (mfl && !seen.has(mfl)) {
      seen.add(mfl)
      out.push(mfl)
    }
  }
  return out
}
