import { describe, expect, it } from 'vitest'
import {
  STEPS,
  canAdvance,
  canResendOtp,
  deliveryState,
  formatCountdown,
  packageTotals,
  previousStage,
  shouldClearOtpAfterVerificationError,
  stepStatus,
} from '@/utils/onboardingSteps'

describe('onboardingSteps', () => {
  it('reports complete, current and upcoming steps', () => {
    expect(STEPS.map((step) => stepStatus(step.key, 'pricing'))).toEqual([
      'complete',
      'complete',
      'current',
    ])
    expect(stepStatus('identity', 'otp')).toBe('current')
    expect(
      STEPS.every((step) => stepStatus(step.key, 'success') === 'complete'),
    ).toBe(true)
  })

  it('lets Back return to editable steps but not past verification', () => {
    expect(previousStage('review')).toBe('pricing')
    expect(previousStage('pricing')).toBe('facilities')
    expect(previousStage('facilities')).toBeNull()
    expect(previousStage('otp')).toBe('identity')
  })

  it('gates each stage on its required input', () => {
    expect(canAdvance('facilities', { selectedFacilityCount: 0 })).toBe(false)
    expect(canAdvance('facilities', { selectedFacilityCount: 2 })).toBe(true)
    expect(canAdvance('pricing', { hasNetwork: true, packageCode: '' })).toBe(
      false,
    )
    expect(
      canAdvance('pricing', { hasNetwork: true, packageCode: 'TOK' }),
    ).toBe(true)
    const ready = {
      accountEmail: 'sam@example.com',
      hasNetwork: true,
      packageCode: 'TOK',
      hasTerms: true,
      termsAccepted: true,
    }
    expect(canAdvance('review', ready)).toBe(true)
    expect(canAdvance('review', { ...ready, termsAccepted: false })).toBe(false)
    expect(canAdvance('review', { ...ready, hasNetwork: false })).toBe(false)
    expect(canAdvance('review', { ...ready, hasTerms: false })).toBe(false)
    expect(canAdvance('review', { ...ready, accountEmail: 'nope' })).toBe(false)
  })

  it('multiplies server price, VAT and gross by facility count without drift', () => {
    const totals = packageTotals(
      {
        price_ex_vat: 30000,
        vat_amount: 4800,
        gross_total: 34800,
        currency: 'KES',
        vat_label: 'VAT (16%)',
      },
      3,
    )
    expect(totals).toMatchObject({
      exVat: 90000,
      vat: 14400,
      gross: 104400,
      count: 3,
      vatLabel: 'VAT (16%)',
    })
    expect(totals.perFacility.gross).toBe(34800)
  })

  it('falls back to the plain price for older catalog responses', () => {
    expect(packageTotals({ price: 100 }, 0)).toMatchObject({
      exVat: 100,
      vat: 0,
      gross: 100,
      count: 1,
    })
    expect(packageTotals(null, 1)).toBeNull()
  })

  it('formats the resend countdown', () => {
    expect(formatCountdown(75)).toBe('1:15')
    expect(formatCountdown(5)).toBe('0:05')
    expect(formatCountdown(-3)).toBe('0:00')
  })

  it('maps delivery status to a display state', () => {
    expect(deliveryState(undefined)).toBe('none')
    expect(deliveryState({ status: 'sent' })).toBe('sent')
    expect(deliveryState({ status: 'unavailable' })).toBe('unavailable')
  })

  it('allows immediate retry after failed delivery while keeping the cooldown for sent codes', () => {
    expect(canResendOtp({ status: 'unavailable' }, 60)).toBe(true)
    expect(canResendOtp({ status: 'sent' }, 60)).toBe(false)
    expect(canResendOtp({ status: 'sent' }, 0)).toBe(true)
    expect(canResendOtp({ status: 'unavailable' }, 60, true)).toBe(false)
  })

  it('keeps the entered code only when the ownership service can be retried', () => {
    expect(
      shouldClearOtpAfterVerificationError('FacilityOwnershipUnavailable'),
    ).toBe(false)
    expect(shouldClearOtpAfterVerificationError('ValidationError')).toBe(true)
    expect(shouldClearOtpAfterVerificationError()).toBe(true)
  })
})
