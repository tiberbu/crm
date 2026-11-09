/** Pure helpers for the coupon admin UI. Kept dependency-free so they are unit-tested. */

export const VALUE_TYPES = {
  flat_tokens: 'Flat tokens',
  percentage_of_purchase: '% of purchase',
}

/** Token value: "1,000 tokens" or "5% of purchase" or "5% of purchase (max 500)". */
export function couponTokenLabel(coupon) {
  const value = Number(coupon?.value || 0)
  if (coupon?.value_type === 'percentage_of_purchase') {
    let label = `${value}% of purchase`
    const cap = Number(coupon?.max_tokens || 0)
    if (cap > 0) label += ` (max ${cap.toLocaleString()})`
    return label
  }
  return `${value.toLocaleString()} tokens`
}

/** Fixed plan value: "5% off Fixed". */
export function couponDiscountLabel(coupon) {
  return `${Number(coupon?.fixed_discount_percent || 0)}% off Fixed`
}

/**
 * Human value for the coupon's plans (P-108). A Flex coupon (and any coupon from before plans
 * existed) reads as its token value; Fixed as "5% off Fixed"; Both as "1,000 tokens on Flex · 5% off Fixed".
 */
export function couponValueLabel(coupon) {
  const plan = coupon?.applies_to || 'Flex'
  if (plan === 'Fixed') return couponDiscountLabel(coupon)
  if (plan === 'Both')
    return `${couponTokenLabel(coupon)} on Flex · ${couponDiscountLabel(coupon)}`
  return couponTokenLabel(coupon)
}

export const PLAN_LABELS = {
  Flex: 'Flex',
  Fixed: 'Fixed',
  Both: 'Flex and Fixed',
}

/** The effective status shown in the list: Revoked > Inactive > Scheduled > Expired > Exhausted > Active. */
export function derivedStatus(coupon) {
  if (coupon?.status === 'Revoked') return 'Revoked'
  if (coupon?.status === 'Inactive') return 'Inactive'
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
  Inactive: 'gray',
  Scheduled: 'blue',
  Expired: 'orange',
  Exhausted: 'gray',
}

/** Split free-text (comma- or newline-separated) into trimmed, unique, non-empty MFL codes. */
export function parseMflList(text) {
  const seen = new Set()
  const out = []
  for (const part of String(text || '')
    .replace(/\n/g, ',')
    .split(',')) {
    const mfl = part.trim()
    if (mfl && !seen.has(mfl)) {
      seen.add(mfl)
      out.push(mfl)
    }
  }
  return out
}

/** Case-insensitive match on network name, network ID, coupon title or code. Empty query matches all. */
export function couponMatches(coupon, query) {
  const q = String(query || '')
    .trim()
    .toLowerCase()
  if (!q) return true
  return [
    coupon?.network_name,
    coupon?.network,
    coupon?.coupon_title,
    coupon?.coupon_code,
  ].some((v) =>
    String(v || '')
      .toLowerCase()
      .includes(q),
  )
}
