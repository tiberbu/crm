// Step state and display maths for the facility onboarding wizard. Prices shown
// here are display values only; the server re-resolves package, price and VAT.

export const STEPS = [
  { key: 'identity', label: 'Identity', stages: ['identity', 'otp'] },
  { key: 'facilities', label: 'Facilities', stages: ['facilities'] },
  { key: 'pricing', label: 'Package', stages: ['pricing'] },
  { key: 'review', label: 'Submit', stages: ['review'] },
]

const PREVIOUS = { otp: 'identity', pricing: 'facilities', review: 'pricing' }

export function stepStatus(stepKey, stage) {
  if (stage === 'success') return 'complete'
  const current = STEPS.findIndex((step) => step.stages.includes(stage))
  const index = STEPS.findIndex((step) => step.key === stepKey)
  if (index < current) return 'complete'
  return index === current ? 'current' : 'upcoming'
}

// The identity is already verified once facilities are shown, so Back stops there;
// changing it means starting over.
export function previousStage(stage) {
  return PREVIOUS[stage] || null
}

export function canAdvance(stage, state) {
  if (stage === 'facilities') return state.selectedFacilityCount > 0
  if (stage === 'pricing') return Boolean(state.hasNetwork && state.packageCode)
  if (stage === 'review') {
    const email = String(state.accountEmail || '').trim()
    return Boolean(
      /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) &&
      state.termsAccepted,
    )
  }
  return true
}

const round2 = (value) => Math.round((Number(value) || 0) * 100) / 100

export function packageTotals(pkg, facilityCount = 1) {
  if (!pkg) return null
  const count = Math.max(1, Number(facilityCount) || 1)
  const exVat = round2(pkg.price_ex_vat ?? pkg.price)
  const vat = round2(pkg.vat_amount)
  const gross = round2(pkg.gross_total ?? exVat + vat)
  return {
    currency: pkg.currency || 'KES',
    vatLabel: pkg.vat_label || 'VAT',
    perFacility: { exVat, vat, gross },
    exVat: round2(exVat * count),
    vat: round2(vat * count),
    gross: round2(gross * count),
    count,
  }
}

export function formatCountdown(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0))
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

// 'sent' shows the masked destination; 'unavailable' offers a retry; 'none' is before any challenge.
export function deliveryState(delivery) {
  if (!delivery) return 'none'
  return delivery.status === 'unavailable' ? 'unavailable' : 'sent'
}

export function canResendOtp(delivery, resendIn, busy = false) {
  return (
    !busy &&
    (delivery?.status === 'unavailable' || Number(resendIn || 0) <= 0)
  )
}

export function shouldClearOtpAfterVerificationError(errorType) {
  return String(errorType || '') !== 'FacilityOwnershipUnavailable'
}
