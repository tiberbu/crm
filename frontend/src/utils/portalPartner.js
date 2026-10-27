// Self-onboarding without a Partner Coupon records the "no-network" Network so staff can find
// the request. It is not a partner, so the portal shows nothing rather than "No Network".
const NO_PARTNER_VALUES = new Set(['no-network', 'no network'])

export function partnerName(value) {
  const name = String(value || '').trim()
  return NO_PARTNER_VALUES.has(name.toLowerCase()) ? '' : name
}

// Price excl. VAT per token, or null for a free package or one without tokens.
export function pricePerToken(pkg) {
  const price = Number(pkg?.price_ex_vat ?? pkg?.price ?? 0)
  const tokens = Number(pkg?.token_quantity || 0)
  return price > 0 && tokens > 0 ? price / tokens : null
}

// A package summary as one line per sentence, for a checklist instead of a paragraph. Decimal
// points ("KES 6.00/token") are not sentence ends; the closing full stop is dropped, and an
// inline "•" separator reads as a comma so a line does not wrap on a bullet.
export function summaryLines(text) {
  return String(text || '')
    .split(/(?<=[.!?])\s+(?=[A-Z0-9~(+])/)
    .map((line) => line.trim().replace(/\s*•\s*/g, ', ').replace(/\.$/, ''))
    .filter(Boolean)
}
