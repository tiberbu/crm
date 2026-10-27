// Value Express display rules for onboarding. They mirror crm/utils/value_express.py so
// cards and totals match what the server charges; the server re-prices every choice.

export const CUSTOM = '__custom__'
export const TOKENS_PER_JOURNEY = 40

const levelKey = (value) =>
  String(value || '')
    .normalize('NFKC')
    .replace(/[\u200b\u2060\ufeff]/g, ' ')
    .split(/\s+/)
    .filter(Boolean)
    .join(' ')
    .toLowerCase()

export function journeys(tokens) {
  return Math.floor(Math.max(0, Number(tokens) || 0) / TOKENS_PER_JOURNEY)
}

// Price per token to the cent, as published on the cards (6.00, 5.36, 4.80).
export function perTokenRate(pkg) {
  const tokens = Number(pkg?.token_quantity) || 0
  const price = Number(pkg?.price_ex_vat ?? pkg?.price) || 0
  return tokens > 0 && price > 0 ? Math.round((price / tokens) * 100) / 100 : 0
}

// "Includes 12% more tokens" against the entry package's rate.
export function morePercent(pkg, packages) {
  const rates = (packages || []).map(perTokenRate).filter(Boolean)
  const base = Math.max(...rates, 0)
  const rate = perTokenRate(pkg)
  const extra = rate && base ? Math.round((base / rate - 1) * 100) : 0
  return extra > 0 ? extra : 0
}

// Any amount, priced at the rate of the highest tier it reaches; tokens rounded down,
// charged tokens × rate (never more than the amount).
export function customQuote(amount, offer) {
  const tiers = offer?.tiers || []
  const minTokens = Number(offer?.min_tokens) || 1000
  const value = Math.max(0, Math.floor(Number(amount) || 0))
  if (!tiers.length)
    return { ok: false, amount: value, tokens: 0, rate: 0, tier: '', charge: 0 }
  let tier = tiers[0]
  for (const candidate of tiers)
    if (value >= candidate.from_amount) tier = candidate
  // Whole cents, so the count matches the server's decimal arithmetic.
  const tokens = Math.floor((value * 100) / Math.round(tier.rate * 100))
  const charge = Math.round(tokens * tier.rate * 100) / 100
  return {
    ok: tokens >= minTokens,
    amount: value,
    tokens,
    rate: tier.rate,
    tier: tier.name,
    charge,
  }
}

// The Fixed package whose levels include the facility's registry level.
export function fixedForLevel(level, fixedPackages) {
  const key = levelKey(level)
  if (!key) return null
  return (
    (fixedPackages || []).find((pkg) =>
      (pkg.facility_levels || []).some((item) => levelKey(item) === key),
    ) || null
  )
}

// "Get started" on the landing page carries ?plan=flex&package=CODE, ?plan=fixed or ?plan=custom&amount=N.
export function parseCarriedChoice(search) {
  const params = new URLSearchParams(search || '')
  const plan = params.get('plan')
  if (plan === 'fixed') return { plan: 'fixed' }
  if (plan === 'custom') {
    const amount = Math.floor(Number(params.get('amount')) || 0)
    return { plan: 'flex', package: CUSTOM, amount: amount > 0 ? amount : null }
  }
  if (plan === 'flex')
    return { plan: 'flex', package: params.get('package') || null }
  return null
}

// Tokens left for services in the first funded month.
export function monthOneTokens(tokens, bonus, access) {
  return Math.max(
    0,
    (Number(tokens) || 0) + (Number(bonus) || 0) - (Number(access) || 0),
  )
}

const PERIOD_UNITS = {
  Monthly: 'month',
  Quarterly: 'quarter',
  'Semi-annual': 'half-year',
  Annual: 'year',
}
export const PERIOD_MONTHS = {
  Monthly: 1,
  Quarterly: 3,
  'Semi-annual': 6,
  Annual: 12,
}

// "per month", "per quarter", "per half-year" or "per year" for a billing period.
export function periodLabel(period) {
  return `per ${PERIOD_UNITS[period] || 'month'}`
}

// Columns for a card grid: at most `most` a row, rows as even as possible (5 → 3+2, 7 → 4+3).
export function gridColumns(count, most = 4) {
  const n = Math.max(0, Math.floor(Number(count) || 0))
  if (n <= most) return Math.max(n, 1)
  return Math.ceil(n / Math.ceil(n / most))
}
