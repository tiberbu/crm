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

