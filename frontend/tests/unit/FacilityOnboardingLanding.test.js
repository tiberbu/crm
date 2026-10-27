import { createApp, nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

const call = vi.hoisted(() => vi.fn())
vi.mock('frappe-ui', async () => {
  const { h } = await import('vue')
  return {
    call,
    Dialog: {
      props: ['open', 'title'],
      setup(props, { slots }) {
        return () =>
          props.open
            ? h(
                'div',
                {
                  role: 'dialog',
                  'aria-modal': 'true',
                  'aria-label': props.title,
                },
                slots.default?.(),
              )
            : null
      },
    },
  }
})

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
  await checkInput(reviewForm.querySelector('[data-testid="terms-acceptance"]'))
  expect(
    reviewForm.querySelector('[data-testid="verified-account-email"]')
      ?.textContent,
  ).toContain('sam@example.com')
  return reviewForm
}

describe('FacilityOnboardingLanding', () => {
  it('recovers from an HFR outage using the verified session without another OTP', async () => {
    call
      .mockResolvedValueOnce({
        message: {
          data: {
            session_token: 'opaque-session',
            delivery: {
              channel: 'sms',
              masked_destination: '254******78',
              status: 'sent',
              resend_after: 60,
            },
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
            identity: {
              full_name: 'Amina Otieno',
              email: 'a***@example.test',
              phone: '254******78',
            },
            account_email: 'sam@example.com',
            facilities: [
              {
                facility_id: 'FID-1',
                facility_name: 'Alpha Clinic',
                facility_level: 'Level 3',
                onboarding_eligible: true,
              },
              {
                facility_id: 'FID-2',
                facility_name: 'Unapproved Clinic',
                facility_level: 'Level 2',
                onboarding_eligible: false,
                facility_eligibility_reason: 'level_not_allowed',
              },
              {
                facility_id: 'FID-3',
                facility_name: 'Facility without a level',
                onboarding_eligible: false,
                facility_eligibility_reason: 'missing_level',
              },
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
      button.textContent.includes('Start your onboarding'),
    )
    startButton.click()
    await nextTick()

    await submitIdentity(host)
    expect(call.mock.calls[0][0]).toContain('start_identity')
    expect(host.textContent).toContain('text message')
    expect(host.textContent).toContain('254******78')
    expect(host.textContent).not.toContain('Amina Otieno')

    await submitOtp(host)
    expect(host.textContent).toContain('Your contact is verified')
    expect(host.textContent).toContain('Retry facility lookup')

    const retryButton = [...host.querySelectorAll('button')].find((button) =>
      button.textContent.includes('Retry facility lookup'),
    )
    retryButton.click()
    await settle()

    expect(host.textContent).toContain('Alpha Clinic')
    expect(host.textContent).toContain('Unapproved Clinic')
    expect(host.textContent).toContain(
      'This facility’s level isn’t currently eligible for online onboarding.',
    )
    expect(host.textContent).toContain('Facility without a level')
    expect(host.textContent).toContain(
      'We couldn’t confirm this facility’s level in the registry',
    )
    expect(host.querySelectorAll('input[type="checkbox"]')[0].disabled).toBe(
      false,
    )
    expect(host.querySelectorAll('input[type="checkbox"]')[1].disabled).toBe(
      true,
    )
    expect(host.querySelectorAll('input[type="checkbox"]')[2].disabled).toBe(
      true,
    )
    expect(host.textContent).toContain('Verified identity')
    expect(host.textContent).toContain('Amina Otieno')
    expect(host.textContent).toContain('a***@example.test')
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
            account_email: 'sam@example.com',
            facilities: [
              {
                facility_id: 'FID-1',
                facility_name: 'Alpha Clinic',
                onboarding_eligible: true,
              },
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
      button.textContent.includes('Start your onboarding'),
    )
    startButton.click()
    await nextTick()

    await submitIdentity(host)
    await submitOtp(host)

    expect(host.textContent).toContain('Alpha Clinic')
    expect(host.textContent).toContain('Verified identity')
    expect(host.textContent).toContain('Amina Otieno')
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
      button.textContent.includes('Start your onboarding'),
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
            account_email: 'sam@example.com',
            facilities: [
              {
                facility_id: 'FID-1',
                facility_name: 'Alpha Clinic',
                onboarding_eligible: true,
              },
            ],
          },
        },
      })
      .mockResolvedValueOnce({
        message: {
          data: {
            network: { name: 'NET-A', display_name: 'Network A' },
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
    const reviewForm = host.querySelector('form')
    const termsLink = [...reviewForm.querySelectorAll('button')].find((button) =>
      button.textContent.includes('Read the complete Terms'),
    )
    expect(termsLink.getAttribute('aria-haspopup')).toBe('dialog')
    termsLink.click()
    await nextTick()
    expect(host.querySelector('[role="dialog"]')?.textContent).toContain(
      'Review these applicable Terms.',
    )
    expect(host.querySelector('[role="dialog"]')?.getAttribute('aria-modal')).toBe(
      'true',
    )
    host.querySelector('[role="dialog"]')?.remove()

    expect(host.querySelector('input[type="email"]')).toBeNull()
    expect(host.textContent).not.toContain('sam@example.com')
    await checkInput(reviewForm.querySelector('[data-testid="terms-acceptance"]'))
    expect(
      reviewForm.querySelector('[data-testid="verified-account-email"]')
        ?.textContent,
    ).toContain('sam@example.com')
    expect(reviewForm.querySelector('input[type="email"]')).toBeNull()
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
    expect(host.textContent).toContain('Your request has been submitted')
  })

  it('displays existing identity message and skips new identity creation on success when account is linked', async () => {
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
            account_email: 'sam@example.com',
            facilities: [
              {
                facility_id: 'FID-1',
                facility_name: 'Alpha Clinic',
                onboarding_eligible: true,
              },
            ],
          },
        },
      })
      .mockResolvedValueOnce({
        message: {
          data: {
            network: { name: 'NET-A', display_name: 'Network A' },
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
        message: {
          data: {
            outcome: 'new',
            allowed_facility_ids: ['FID-1'],
            is_existing_identity: true,
          },
        },
      })
      .mockResolvedValueOnce({
        message: {
          data: {
            outcome: 'new',
            portal_status: 'linked',
            is_existing_identity: true,
            submissions: [{ submission: 'OIS-1', facility: 'Alpha Clinic', mfl_code: '10001' }],
            enrollments: [{ facility: 'Alpha Clinic', mfl_code: '10001' }],
          },
        },
      })

    const host = document.createElement('div')
    document.body.append(host)
    const app = createApp(FacilityOnboardingLanding)
    app.config.globalProperties.__ = globalThis.__
    app.mount(host)
    mountedApps.push(app)

    const reviewForm = await goToReview(host)
    await submitForm(reviewForm)

    expect(host.textContent).toContain('Your request has been submitted')
    expect(host.textContent).toContain(
      'Your selected facilities are linked to your existing Tiberbu Express account. Sign in with your usual details to review your draft order and pay its invoice. Tokens are added once payment is received.',
    )
    expect(host.querySelector('[data-testid="linked-identity-note"]')).not.toBeNull()
    expect(host.textContent).toContain('Sign in to Tiberbu Express')
  })

  it('continues submission and links account when conflict preflight returns outcome existing_identity', async () => {
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
            account_email: 'sam@example.com',
            facilities: [
              {
                facility_id: 'FID-1',
                facility_name: 'Alpha Clinic',
                onboarding_eligible: true,
              },
            ],
          },
        },
      })
      .mockResolvedValueOnce({
        message: {
          data: {
            network: { name: 'NET-A', display_name: 'Network A' },
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
        message: {
          data: {
            outcome: 'existing_identity',
            allowed_facility_ids: ['FID-1'],
          },
        },
      })
      .mockResolvedValueOnce({
        message: {
          data: {
            outcome: 'new',
            portal_status: 'linked',
            is_existing_identity: true,
            submissions: [{ submission: 'OIS-1', facility: 'Alpha Clinic', mfl_code: '10001' }],
            enrollments: [{ facility: 'Alpha Clinic', mfl_code: '10001' }],
          },
        },
      })

    const host = document.createElement('div')
    document.body.append(host)
    const app = createApp(FacilityOnboardingLanding)
    app.config.globalProperties.__ = globalThis.__
    app.mount(host)
    mountedApps.push(app)

    const reviewForm = await goToReview(host)
    await submitForm(reviewForm)

    expect(host.textContent).toContain('Your request has been submitted')
    expect(host.textContent).toContain(
      'Your selected facilities are linked to your existing Tiberbu Express account. Sign in with your usual details to review your draft order and pay its invoice. Tokens are added once payment is received.',
    )
    expect(host.querySelector('[data-testid="linked-identity-note"]')).not.toBeNull()
    expect(host.textContent).toContain('Sign in to Tiberbu Express')
  })

  it.each([
    [
      'facility_review returned by locked submit recheck',
      { outcome: 'new', allowed_facility_ids: ['FID-1'] },
      { outcome: 'facility_review', allowed_facility_ids: [] },
      'Alpha Clinic',
    ],
    [
      'facility level eligibility changed',
      {
        outcome: 'facility_level_ineligible',
        allowed_facility_ids: [],
        ineligible_facility_ids: ['FID-1'],
        facility_eligibility: [
          {
            facility_id: 'FID-1',
            onboarding_eligible: false,
            facility_eligibility_reason: 'level_not_allowed',
          },
          {
            facility_id: 'FID-2',
            onboarding_eligible: false,
            facility_eligibility_reason: 'missing_level',
          },
        ],
      },
      null,
      'Facility level eligibility changed while you were onboarding',
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
              account_email: 'sam@example.com',
              facilities: [
                {
                  facility_id: 'FID-1',
                  facility_name: 'Alpha Clinic',
                  onboarding_eligible: true,
                },
                {
                  facility_id: 'FID-2',
                  facility_name: 'Facility without a level',
                  onboarding_eligible: true,
                },
              ],
            },
          },
        })
        .mockResolvedValueOnce({
          message: {
            data: {
              network: {
                name: 'NET-A',
                display_name: 'Network A',
                contact_email: 'support@example.test',
              },
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
      expect(host.textContent).not.toContain('Your request has been submitted')
      if (_outcome === 'existing_identity' || submitConflict) {
        expect(
          host.querySelector('[data-testid="duplicate-signin"]')?.textContent,
        ).toContain('Sign in to Tiberbu Express')
        expect(
          host.querySelector('[data-testid="duplicate-support"]')?.textContent,
        ).toContain('Contact support')
      }
      if (_outcome === 'facility level eligibility changed') {
        expect(
          host.querySelector('[data-testid="duplicate-signin"]'),
        ).toBeNull()
        expect(
          host.querySelector('[data-testid="duplicate-support"]'),
        ).toBeNull()
        expect(
          [...host.querySelectorAll('input[type="checkbox"]')].every(
            (input) => input.disabled,
          ),
        ).toBe(true)
        expect(host.textContent).toContain(
          'We couldn’t confirm this facility’s level in the registry',
        )
      }
    },
  )
})
