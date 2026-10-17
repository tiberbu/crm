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
import OtpCodeInput from '@/components/FacilityOnboarding/OtpCodeInput.vue'
import TokenCalculator from '@/components/TokenCalculator.vue'

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

describe('Onboarding Mobile Responsiveness Across Flow', () => {
  it('OtpCodeInput renders touch-friendly compact boxes on narrow screens', () => {
    const host = document.createElement('div')
    document.body.append(host)
    const app = createApp(OtpCodeInput, {
      modelValue: '',
      label: 'Verification code',
    })
    app.mount(host)
    mountedApps.push(app)

    const inputs = host.querySelectorAll('input')
    expect(inputs).toHaveLength(6)
    for (const input of inputs) {
      // Must include mobile size-10 and desktop sm:size-14
      expect(input.className).toContain('size-10')
      expect(input.className).toContain('sm:size-14')
      expect(input.className).toContain('text-lg')
    }
  })

  it('Welcome stage renders responsive header, mobile sign-in button, and touch CTA', async () => {
    const host = document.createElement('div')
    document.body.append(host)
    const app = createApp(FacilityOnboardingLanding)
    app.config.globalProperties.__ = (text) => text
    app.mount(host)
    mountedApps.push(app)

    // Header sign-in link has shortened text on mobile
    const signInLink = host.querySelector('a[href="/login?redirect-to=/cx-portal"]')
    expect(signInLink).toBeTruthy()
    expect(signInLink.querySelector('.sm\\:hidden')?.textContent).toBe('Sign in')

    // Start onboarding button is full width on mobile
    const startBtn = [...host.querySelectorAll('button')].find((b) =>
      b.textContent.includes('Start secure onboarding'),
    )
    expect(startBtn.className).toContain('w-full')
    expect(startBtn.className).toContain('sm:w-auto')
  })

  it('Identity stage inputs use text-base to prevent iOS Safari auto-zoom', async () => {
    const host = document.createElement('div')
    document.body.append(host)
    const app = createApp(FacilityOnboardingLanding)
    app.config.globalProperties.__ = (text) => text
    app.mount(host)
    mountedApps.push(app)

    const startBtn = [...host.querySelectorAll('button')].find((b) =>
      b.textContent.includes('Start secure onboarding'),
    )
    startBtn.click()
    await nextTick()

    const select = host.querySelector('select')
    const idInput = host.querySelector('input[placeholder="Enter your ID number"]')

    expect(select.className).toContain('text-base')
    expect(select.className).toContain('sm:text-sm')

    expect(idInput.className).toContain('text-base')
    expect(idInput.className).toContain('sm:text-sm')
  })

  it('Stepper adapts with compact size and responsive labels', async () => {
    const host = document.createElement('div')
    document.body.append(host)
    const app = createApp(FacilityOnboardingLanding)
    app.config.globalProperties.__ = (text) => text
    app.mount(host)
    mountedApps.push(app)

    host.querySelector('button').click()
    await nextTick()

    const stepper = host.querySelector('ol[aria-label="Onboarding steps"]')
    expect(stepper).toBeTruthy()
    expect(stepper.className).toContain('grid-cols-4')
    expect(stepper.className).toContain('gap-1.5')

    const stepIcons = stepper.querySelectorAll('li span.rounded-lg')
    expect(stepIcons[0].className).toContain('size-6')
    expect(stepIcons[0].className).toContain('sm:size-8')
  })

  it('Pricing stage multi-facility summary table wraps with min-w-[500px] and overflow-x-auto', async () => {
    call
      .mockResolvedValueOnce({
        message: {
          data: {
            session_token: 'test-session',
            delivery: { status: 'sent', resend_after: 60 },
          },
        },
      })
      .mockResolvedValueOnce({
        message: {
          data: {
            state: 'ready',
            identity: { full_name: 'Dr. Jane' },
            account_email: 'jane@example.com',
            facilities: [
              { facility_id: 'F1', facility_name: 'Clinic Alpha', mfl_code: '101', onboarding_eligible: true },
              { facility_id: 'F2', facility_name: 'Clinic Beta', mfl_code: '102', onboarding_eligible: true },
            ],
          },
        },
      })
      .mockResolvedValueOnce({
        message: {
          data: {
            network: { name: 'NET-1', display_name: 'CareVerse Network' },
            packages: [
              { item_code: 'CV-TOKEN-FREE', display_name: 'Free Trial', price_ex_vat: 0, token_quantity: 400, currency: 'KES' },
              { item_code: 'CV-TOKEN-STARTER', display_name: 'Starter', price_ex_vat: 6000, token_quantity: 1000, currency: 'KES' },
            ],
          },
        },
      })

    const host = document.createElement('div')
    document.body.append(host)
    const app = createApp(FacilityOnboardingLanding)
    app.config.globalProperties.__ = (text, args) =>
      args ? text.replace(/:(\w+)/g, (_, k) => args[k]) : text
    app.mount(host)
    mountedApps.push(app)

    // Advance to pricing
    host.querySelector('button').click()
    await nextTick()

    await enterInput(host.querySelector('input[placeholder="Enter your ID number"]'), '12345678')
    await submitForm(host.querySelector('form'))

    for (const [index, digit] of [...'123456'].entries()) {
      await enterInput(host.querySelectorAll('input[inputmode="numeric"]')[index], digit)
    }
    await submitForm(host.querySelector('form'))

    const checkboxes = host.querySelectorAll('input[type="checkbox"]')
    for (const cb of checkboxes) {
      if (!cb.disabled) {
        await checkInput(cb)
      }
    }
    await submitForm(host.querySelector('form'))
    await settle()

    // Verify summary table has mobile overflow safety
    const table = host.querySelector('table')
    expect(table).toBeTruthy()
    expect(table.className).toContain('min-w-[500px]')
    expect(table.parentElement.className).toContain('overflow-x-auto')

    // Verify pricing cards have min-h-11 on mobile selection buttons
    const cardButtons = host.querySelectorAll('article button')
    expect(cardButtons.length).toBeGreaterThan(0)
    expect(cardButtons[0].className).toContain('min-h-11')
  })

  it('TokenCalculator stacks clinical scope buttons and prevents iOS zoom on inputs', () => {
    const host = document.createElement('div')
    document.body.append(host)
    const app = createApp(TokenCalculator, {
      packages: [
        { item_code: 'CV-TOKEN-STARTER', display_name: 'Starter', price_ex_vat: 6000, tokens: 1000, currency: 'KES' },
      ],
      facilityName: 'Test Clinic',
    })
    app.mount(host)
    mountedApps.push(app)

    // Clinical Scope buttons container
    const scopeContainer = host.querySelector('.grid-cols-1.sm\\:grid-cols-2')
    expect(scopeContainer).toBeTruthy()

    // Average bill input has text-base on mobile
    const billInput = host.querySelector('input[type="number"][step="250"]')
    expect(billInput).toBeTruthy()
    expect(billInput.className).toContain('text-base')
    expect(billInput.className).toContain('sm:text-sm')
  })
})
