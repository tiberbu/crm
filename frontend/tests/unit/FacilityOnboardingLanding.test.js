import { createApp, nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

const call = vi.hoisted(() => vi.fn())
vi.mock('frappe-ui', () => ({ call }))

import FacilityOnboardingLanding from '@/pages/FacilityOnboarding/FacilityOnboardingLanding.vue'

const mountedApps = []

afterEach(() => {
  mountedApps.splice(0).forEach((app) => app.unmount())
  document.body.innerHTML = ''
  call.mockReset()
})

async function settle() {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
  await nextTick()
}

async function enterInput(input, value) {
  input.value = value
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await nextTick()
}

async function checkInput(input) {
  input.checked = true
  input.dispatchEvent(new Event('change', { bubbles: true }))
  await nextTick()
}

async function submitForm(form) {
  const submitButton = form.querySelector('button:not([type="button"])')
  expect(submitButton).toBeTruthy()
  expect(submitButton.disabled).toBe(false)
  submitButton.click()
  await settle()
}

async function submitIdentity(host) {
  const form = host.querySelector('form')
  const identityInput = form.querySelector(
    'input[placeholder="Enter your ID number"]',
  )
  expect(identityInput.required).toBe(true)
  await enterInput(identityInput, '12345678')
  await submitForm(form)
}

async function submitOtp(host) {
  const form = host.querySelector('form')
  const otpInputs = [...form.querySelectorAll('input[inputmode="numeric"]')]
  expect(otpInputs).toHaveLength(6)
  for (const [index, digit] of [...'123456'].entries()) {
    const input = form.querySelectorAll('input[inputmode="numeric"]')[index]
    await enterInput(input, digit)
  }
  await submitForm(form)
}

async function goToReview(host) {
  host.querySelector('button').click()
  await nextTick()
  await submitIdentity(host)
  await submitOtp(host)
  await checkInput(host.querySelector('input[type="checkbox"]'))
  await submitForm(host.querySelector('form'))
  await settle()
  await submitForm(host.querySelector('form'))
  const reviewForm = host.querySelector('form')
  await enterInput(
    reviewForm.querySelector('input[placeholder="you@example.com"]'),
    'sam@example.com',
  )
  await checkInput(reviewForm.querySelector('input[type="checkbox"]'))
  return reviewForm
}

describe('FacilityOnboardingLanding', () => {
  it('recovers from an HFR outage using the verified session without another OTP', async () => {
    call
      .mockResolvedValueOnce({
        message: {
          data: {
            session_token: 'opaque-session',
            delivery: { status: 'sent', resend_after: 60 },
          },
        },
      })
      .mockResolvedValueOnce({
        message: { data: { state: 'hfr_pending', retryable: true } },
      })
      .mockResolvedValueOnce({
        message: {
          data: {
            state: 'ready',
            identity: { full_name: 'Amina Otieno' },
            facilities: [
              { facility_id: 'FID-1', facility_name: 'Alpha Clinic' },
            ],
          },
        },
      })

    const host = document.createElement('div')
    document.body.append(host)
    const app = createApp(FacilityOnboardingLanding)
    app.config.globalProperties.__ = globalThis.__
    app.mount(host)
    mountedApps.push(app)

    const startButton = [...host.querySelectorAll('button')].find((button) =>
      button.textContent.includes('Start secure onboarding'),
    )
    startButton.click()
    await nextTick()

    await submitIdentity(host)
    expect(call.mock.calls[0][0]).toContain('start_identity')

    await submitOtp(host)
    expect(host.textContent).toContain('Your contact is verified')
    expect(host.textContent).toContain('Retry facility lookup')

    const retryButton = [...host.querySelectorAll('button')].find((button) =>
      button.textContent.includes('Retry facility lookup'),
    )
    retryButton.click()
    await settle()

    expect(host.textContent).toContain('Alpha Clinic')
    expect(call.mock.calls.map(([method]) => method.split('.').at(-1))).toEqual(
      ['start_identity', 'verify_otp', 'retry_hfr'],
    )
    expect(call.mock.calls[2][1]).toEqual({ session_token: 'opaque-session' })
  })

  it('recovers a lost OTP verification response through the verified session', async () => {
    call
      .mockResolvedValueOnce({
        message: {
          data: {
            session_token: 'opaque-session',
            delivery: { status: 'sent', resend_after: 60 },
          },
        },
      })
      .mockRejectedValueOnce(new Error('Network error'))
      .mockResolvedValueOnce({
        message: {
          data: {
            state: 'ready',
            identity: { full_name: 'Amina Otieno' },
            facilities: [
              { facility_id: 'FID-1', facility_name: 'Alpha Clinic' },
            ],
          },
        },
      })

    const host = document.createElement('div')
    document.body.append(host)
    const app = createApp(FacilityOnboardingLanding)
    app.config.globalProperties.__ = globalThis.__
    app.mount(host)
    mountedApps.push(app)

    const startButton = [...host.querySelectorAll('button')].find((button) =>
      button.textContent.includes('Start secure onboarding'),
    )
    startButton.click()
    await nextTick()

    await submitIdentity(host)
    await submitOtp(host)

    expect(host.textContent).toContain('Alpha Clinic')
    expect(call.mock.calls.map(([method]) => method.split('.').at(-1))).toEqual(
      ['start_identity', 'verify_otp', 'retry_hfr'],
    )
    expect(call.mock.calls[2][1]).toEqual({ session_token: 'opaque-session' })
  })

  it('shows support guidance and disables retry after the HFR limit', async () => {
    call
      .mockResolvedValueOnce({
        message: {
          data: {
            session_token: 'opaque-session',
            delivery: { status: 'sent', resend_after: 60 },
          },
        },
      })
      .mockResolvedValueOnce({
        message: { data: { state: 'hfr_pending', retryable: false } },
      })

    const host = document.createElement('div')
    document.body.append(host)
    const app = createApp(FacilityOnboardingLanding)
    app.config.globalProperties.__ = globalThis.__
    app.mount(host)
    mountedApps.push(app)

    const startButton = [...host.querySelectorAll('button')].find((button) =>
      button.textContent.includes('Start secure onboarding'),
    )
    startButton.click()
    await nextTick()
    await submitIdentity(host)
    await submitOtp(host)

    expect(host.textContent).toContain('contact support')
    expect(host.textContent).not.toContain('Retry facility lookup')
    expect(call.mock.calls.map(([method]) => method.split('.').at(-1))).toEqual(
      ['start_identity', 'verify_otp'],
    )
  })

  it('loads and displays Terms before requiring acceptance and submitting its hash', async () => {
    call
      .mockResolvedValueOnce({
        message: {
          data: {
            session_token: 'opaque-session',
            delivery: { status: 'sent', resend_after: 60 },
          },
        },
      })
      .mockResolvedValueOnce({
        message: {
          data: {
            state: 'ready',
            identity: { full_name: 'Amina Otieno' },
            facilities: [
              { facility_id: 'FID-1', facility_name: 'Alpha Clinic' },
            ],
          },
        },
      })
      .mockResolvedValueOnce({
        message: {
          data: {
            network: { display_name: 'Network A' },
            packages: [
              { item_code: 'TOK-1', display_name: 'Starter', price: 1000 },
            ],
          },
        },
      })
      .mockResolvedValueOnce({
        message: {
          data: {
            document: 'Self-Onboarding Terms',
            rendered_html: '<p>Review these applicable Terms.</p>',
            content_hash: 'a'.repeat(64),
          },
        },
      })
      .mockResolvedValueOnce({
        message: { data: { outcome: 'new', allowed_facility_ids: ['FID-1'] } },
      })
      .mockResolvedValueOnce({
        message: {
          data: {
            submissions: [{ submission: 'OIS-1', facility: 'Alpha Clinic' }],
          },
        },
      })

    const host = document.createElement('div')
    document.body.append(host)
    const app = createApp(FacilityOnboardingLanding)
    app.config.globalProperties.__ = globalThis.__
    app.mount(host)
    mountedApps.push(app)

    host.querySelector('button').click()
    await nextTick()
    await submitIdentity(host)
    await submitOtp(host)

    const facilityCheckbox = host.querySelector('input[type="checkbox"]')
    await checkInput(facilityCheckbox)
    await submitForm(host.querySelector('form'))

    await settle()
    await submitForm(host.querySelector('form'))

    expect(call.mock.calls[3][0]).toContain('get_self_onboarding_terms')
    const termsPanel = host.querySelector(
      '[data-testid="self-onboarding-terms"]',
    )
    expect(termsPanel.textContent).toContain('Self-Onboarding Terms')
    expect(termsPanel.textContent).toContain('Review these applicable Terms.')

    const reviewForm = host.querySelector('form')
    const submitButton = reviewForm.querySelector('button:not([type="button"])')
    expect(submitButton.disabled).toBe(true)
    await enterInput(
      reviewForm.querySelector('input[placeholder="you@example.com"]'),
      'sam@example.com',
    )
    expect(submitButton.disabled).toBe(true)
    await checkInput(reviewForm.querySelector('input[type="checkbox"]'))
    await submitForm(reviewForm)

    expect(call.mock.calls.map(([method]) => method.split('.').at(-1))).toEqual(
      [
        'start_identity',
        'verify_otp',
        'get_catalog',
        'get_self_onboarding_terms',
        'check_onboarding_conflicts',
        'submit_onboarding',
      ],
    )
    expect(call.mock.calls[4][1]).toMatchObject({
      partner_id: '',
      selected_facility_ids: '["FID-1"]',
    })
    expect(call.mock.calls[5][1]).toMatchObject({
      terms_accepted: 1,
      accepted_terms_hash: 'a'.repeat(64),
    })
    expect(host.textContent).toContain('Your onboarding has started')
  })

  it.each([
    [
      'existing_identity',
      { outcome: 'existing_identity', allowed_facility_ids: [] },
      null,
      'An onboarding request already exists for this identity',
    ],
    [
      'facility_review returned by locked submit recheck',
      { outcome: 'new', allowed_facility_ids: ['FID-1'] },
      { outcome: 'facility_review', allowed_facility_ids: [] },
      'Alpha Clinic',
    ],
  ])(
    'stops submission safely for a %s conflict',
    async (_outcome, conflict, submitConflict, expectedCopy) => {
      call
        .mockResolvedValueOnce({
          message: {
            data: {
              session_token: 'opaque-session',
              delivery: { status: 'sent', resend_after: 60 },
            },
          },
        })
        .mockResolvedValueOnce({
          message: {
            data: {
              state: 'ready',
              identity: { full_name: 'Amina Otieno' },
              facilities: [
                { facility_id: 'FID-1', facility_name: 'Alpha Clinic' },
              ],
            },
          },
        })
        .mockResolvedValueOnce({
          message: {
            data: {
              network: { display_name: 'Network A' },
              packages: [
                { item_code: 'TOK-1', display_name: 'Starter', price: 1000 },
              ],
            },
          },
        })
        .mockResolvedValueOnce({
          message: {
            data: {
              document: 'Self-Onboarding Terms',
              rendered_html: '<p>Review these applicable Terms.</p>',
              content_hash: 'a'.repeat(64),
            },
          },
        })
        .mockResolvedValueOnce({ message: { data: conflict } })
      if (submitConflict) {
        call.mockResolvedValueOnce({ message: { data: submitConflict } })
      }

      const host = document.createElement('div')
      document.body.append(host)
      const app = createApp(FacilityOnboardingLanding)
      app.config.globalProperties.__ = globalThis.__
      app.mount(host)
      mountedApps.push(app)

      const reviewForm = await goToReview(host)
      await submitForm(reviewForm)

      const expectedMethods = [
        'start_identity',
        'verify_otp',
        'get_catalog',
        'get_self_onboarding_terms',
        'check_onboarding_conflicts',
      ]
      if (submitConflict) expectedMethods.push('submit_onboarding')
      expect(
        call.mock.calls.map(([method]) => method.split('.').at(-1)),
      ).toEqual(expectedMethods)
      expect(call.mock.calls[4][1]).toMatchObject({
        session_token: 'opaque-session',
        selected_facility_ids: '["FID-1"]',
      })
      expect(host.textContent).toContain(expectedCopy)
      expect(host.textContent).not.toContain('Your onboarding has started')
    },
  )
})
