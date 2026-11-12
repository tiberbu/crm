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
  if (Number(coupon?.reward_by_level || 0)) return 'By facility level'
  return planValueLabel(coupon)
}

/** The single reward's label for the coupon's plans. */
function planValueLabel(coupon) {
  const plan = coupon?.applies_to || 'Flex'
  if (plan === 'Fixed') return couponDiscountLabel(coupon)
  if (plan === 'Both')
    return `${couponTokenLabel(coupon)} on Flex · ${couponDiscountLabel(coupon)}`
  return couponTokenLabel(coupon)
}

/**
 * P-123: one line per level reward, then "All other levels", e.g.
 * [{ level: 'Level 2', label: '1,000 tokens on Flex · 10% off Fixed' }, …].
 * A plan the row gives nothing for is left out; a row (or the other levels) giving nothing reads "No reward".
 */
export function couponLevelLines(coupon) {
  if (!Number(coupon?.reward_by_level || 0)) return []
  const plan = coupon?.applies_to || 'Flex'
  const describe = (value, discount) => {
    const parts = []
    const reward = { ...coupon, value, fixed_discount_percent: discount }
    if (plan !== 'Fixed' && Number(value || 0) > 0) parts.push(couponTokenLabel(reward))
    if (plan !== 'Flex' && Number(discount || 0) > 0) parts.push(couponDiscountLabel(reward))
    if (!parts.length) return 'No reward'
    if (plan === 'Both' && parts.length === 2) parts[0] += ' on Flex'
    return parts.join(' · ')
  }
  const lines = (coupon?.level_rewards || []).map((row) => ({
    level: row.facility_level,
    label: describe(row.flex_value, row.fixed_discount_percent),
  }))
  lines.push({
    level: 'All other levels',
    label: describe(coupon?.value, coupon?.fixed_discount_percent),
  })
  return lines
}

/**
 * The guest offer for a level-rewarded coupon, levels giving nothing left out:
 * "Level 2: +1,000 tokens; Level 4: +2,500 tokens" (a Fixed-only coupon has no "+", as before).
 */
export function couponOfferByLevel(offer) {
  const plus = (offer?.applies_to || 'Flex') === 'Fixed' ? '' : '+'
  return couponLevelLines(offer)
    .filter((line) => line.label !== 'No reward')
    .map((line) => `${line.level}: ${plus}${line.label}`)
    .join('; ')
}

/** The level-rewards rows the dialog sends: trimmed levels, numbers, blank rows dropped. */
export function cleanLevelRewards(rows) {
  return (rows || [])
    .map((row) => ({
      facility_level: String(row?.facility_level || '')
        .split(/\s+/)
        .filter(Boolean)
        .join(' '),
      flex_value: Number(row?.flex_value || 0),
      fixed_discount_percent: Number(row?.fixed_discount_percent || 0),
    }))
    .filter(
      (row) =>
        row.facility_level || row.flex_value || row.fixed_discount_percent,
    )
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

/**
 * Full Partner Coupon self-onboarding link on the given site base URL, e.g.
 * "https://site.example.test/facility-onboarding?partner_coupon=123456".
 * Trailing slashes on the base are dropped; an empty coupon gives ''.
 */
export function partnerCouponLink(baseUrl, partnerId) {
  const coupon = String(partnerId ?? '').trim()
  if (!coupon) return ''
  const base = String(baseUrl ?? '').trim().replace(/\/+$/, '')
  return `${base}/facility-onboarding?partner_coupon=${encodeURIComponent(coupon)}`
}
