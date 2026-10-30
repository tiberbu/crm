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

const FLEX = [
  { item_code: 'CV-TOKEN-STARTER', display_name: 'Starter', description: 'Small clinics', token_quantity: 1000, price_ex_vat: 6000, vat_amount: 960, gross_total: 6960, vat_rate: 16, vat_label: 'VAT (16%)', currency: 'KES' },
  { item_code: 'CV-TOKEN-GROWTH', display_name: 'Growth', description: 'Growing clinics', token_quantity: 2800, price_ex_vat: 15000, vat_amount: 2400, gross_total: 17400, vat_rate: 16, vat_label: 'VAT (16%)', currency: 'KES', coverage_metrics: '{"badge": "Popular"}' },
  { item_code: 'CV-TOKEN-SCALE', display_name: 'Scale', description: 'Busy clinics', token_quantity: 6250, price_ex_vat: 30000, vat_amount: 4800, gross_total: 34800, vat_rate: 16, vat_label: 'VAT (16%)', currency: 'KES' },
]
const FIXED = [
  { item_code: 'CV-FIXED-L2', display_name: 'Fixed L2', facility_levels: ['Level 2'], price_ex_vat: 15000, vat_amount: 2400, gross_total: 17400, currency: 'KES' },
  { item_code: 'CV-FIXED-L3', display_name: 'Fixed L3', facility_levels: ['Level 3B', 'Level 3C'], price_ex_vat: 18000, vat_amount: 2880, gross_total: 20880, currency: 'KES' },
]
const CUSTOM_OFFER = {
  item_code: 'CV-TOKEN-CUSTOM',
  display_name: 'Custom',
  currency: 'KES',
  min_tokens: 1000,
  min_amount: 6000,
  tiers: [
    { name: 'Starter', from_amount: 6000, rate: 6 },
    { name: 'Growth', from_amount: 15000, rate: 5.36 },
    { name: 'Scale', from_amount: 30000, rate: 4.8 },
  ],
}
const FACILITIES = [
  { facility_id: 'FID-A', facility_name: 'Alpha Clinic', mfl_code: '101', facility_level: 'Level 2', onboarding_eligible: true },
  { facility_id: 'FID-B', facility_name: 'Beta Nursing Home', mfl_code: '102', facility_level: 'Level 3B', onboarding_eligible: true },
  { facility_id: 'FID-C', facility_name: 'Gamma Dispensary', mfl_code: '103', facility_level: 'Level 3A', onboarding_eligible: true },
]

async function advanceToPricing(host, facilitiesList, catalog = {}) {
  call
    .mockResolvedValueOnce({ message: { data: { session_token: 'test-session', delivery: { status: 'sent', resend_after: 60 } } } })
    .mockResolvedValueOnce({ message: { data: { state: 'ready', identity: { full_name: 'Test Owner' }, account_email: 'owner@example.test', facilities: facilitiesList } } })
    .mockResolvedValueOnce({
      message: {
        data: {
          network: { name: 'NET-1', display_name: 'Test Network' },
          packages: FLEX,
          fixed_packages: FIXED,
          custom_offer: CUSTOM_OFFER,
          welcome_bonus_tokens: 400,
          calculator_config: { monthly_platform_fee: 500 },
          ...catalog,
        },
      },
    })
  const app = createApp(FacilityOnboardingLanding)
  app.config.globalProperties.__ = globalThis.__
  app.mount(host)
  mountedApps.push(app)
  await enterInput(host.querySelector('input[placeholder="Enter your ID number"]'), '12345678')
  await submitForm(host.querySelector('form'))
  for (const [index, digit] of [...'123456'].entries()) {
    await enterInput(host.querySelectorAll('input[inputmode="numeric"]')[index], digit)
  }
  await submitForm(host.querySelector('form'))
  for (const cb of host.querySelectorAll('input[type="checkbox"]')) await checkInput(cb)
  await submitForm(host.querySelector('form'))
  await settle()
}

const byText = (host, selector, text) => [...host.querySelectorAll(selector)].find((el) => el.textContent.includes(text))
const sumbarButton = (host) => host.querySelector('.sumbar button.primary')
const sumbarOrContinue = (host) => host.querySelector('form button:not([type="button"])')

describe('Value Express package step', () => {
  afterEach(() => window.history.replaceState(null, '', '/'))

  it('shows each Flex card with tokens, journeys, rate and bonus, and nothing chosen yet', async () => {
    const host = document.createElement('div')
    document.body.append(host)
    await advanceToPricing(host, FACILITIES.slice(0, 1))
    const cards = host.querySelectorAll('[data-testid="package-grid"] .pkg')
    expect(cards).toHaveLength(4)
    const growth = byText(host, '[data-testid="package-grid"] .pkg', 'Growth')
    expect(growth.textContent).toContain('2,800')
    expect(growth.textContent).toContain('70')
    expect(growth.textContent).toContain('KES 5.36')
    expect(growth.textContent).toContain('Includes 12% more tokens')
    expect(growth.querySelector('.rec').textContent).toBe('Popular')
    expect(growth.textContent).toContain('2,700')
    expect(host.textContent).not.toMatch(/\{\d\}/)
    expect(host.querySelector('.factabs')).toBeNull()
    expect(sumbarButton(host).disabled).toBe(true)
    expect(host.querySelector('.hintline').textContent).toBe('Choose a package to continue.')
  })

  it('shows a Suits line only when the package has one, and explains Custom rounding', async () => {
    const host = document.createElement('div')
    document.body.append(host)
    await advanceToPricing(host, FACILITIES.slice(0, 1), {
      packages: [{ ...FLEX[0], audience: 'For small OPD clinics' }, FLEX[1], FLEX[2]],
    })
    expect(byText(host, '[data-testid="package-grid"] .pkg', 'Starter').textContent).toContain('SuitsFor small OPD clinics')
    expect(byText(host, '[data-testid="package-grid"] .pkg', 'Scale').textContent).not.toContain('Suits')
    expect(host.textContent).not.toContain('—Price per token')

    await enterInput(host.querySelector('#custom-amount'), '7000')
    expect(host.querySelector('[data-testid="custom-charge"]').textContent).toBe('KES 6,996.00')
    expect(host.querySelector('[data-testid="custom-rounding"]').textContent).toContain('1,166 whole tokens at KES 6.00 each')
    await enterInput(host.querySelector('#custom-amount'), '7200')
    expect(host.querySelector('[data-testid="custom-rounding"]')).toBeNull()
  })

  it('goes back to the Facility step from the Back button and the stepper', async () => {
    const host = document.createElement('div')
    document.body.append(host)
    await advanceToPricing(host, FACILITIES.slice(0, 1))
    host.querySelector('[data-testid="pricing-back"]').click()
    await nextTick()
    expect(host.querySelector('[data-testid="package-grid"]')).toBeNull()
    expect(host.querySelector('input[type="checkbox"]:checked')).toBeTruthy()
    sumbarOrContinue(host)?.click()
    await settle()
    host.querySelector('[data-testid="step-facilities"]').click()
    await nextTick()
    expect(host.querySelector('[data-testid="package-grid"]')).toBeNull()
    expect(host.querySelector('[data-testid="step-identity"]')).toBeNull()
  })

  it('moves to the next facility once one is set', async () => {
    const host = document.createElement('div')
    document.body.append(host)
    await advanceToPricing(host, FACILITIES.slice(0, 2))
    expect(host.querySelectorAll('.factabs [role="tab"]')).toHaveLength(2)
    expect(host.querySelector('.hintline').textContent).toBe('Choose a package for each facility to continue.')
    byText(host, '[data-testid="package-grid"] .pkg', 'Starter').querySelector('.btn').click()
    await nextTick()
    const next = byText(host, '[data-testid="next-facility"] button', 'Next: Beta Nursing Home')
    expect(next).toBeTruthy()
    next.click()
    await nextTick()
    expect(host.querySelector('[role="tab"][aria-selected="true"]').textContent).toContain('Beta Nursing Home')
    byText(host, '[data-testid="package-grid"] .pkg', 'Scale').querySelector('.btn').click()
    await nextTick()
    expect(host.querySelector('[data-testid="next-facility"]').textContent).toContain('All 2 facilities are set.')
    expect(sumbarButton(host).disabled).toBe(false)
  })

  it('prices Fixed by the facility level and refuses a level without a Fixed fee', async () => {
    const host = document.createElement('div')
    document.body.append(host)
    await advanceToPricing(host, FACILITIES)
    byText(host, '[role="tab"]', 'Beta Nursing Home').click()
    await nextTick()
    const fixed = host.querySelector('[data-testid="plan-fixed"]')
    expect(fixed.textContent).toContain('KES 18,000 per month for your Level 3B facility')
    fixed.click()
    await nextTick()
    const tiers = host.querySelectorAll('[data-testid="fixed-tier"]')
    expect([...tiers].map((tier) => tier.getAttribute('aria-pressed'))).toEqual(['false', 'true'])
    expect(tiers[0].disabled).toBe(true)
    byText(host, '[role="tab"]', 'Gamma Dispensary').click()
    await nextTick()
    expect(host.querySelector('[data-testid="plan-fixed"]').disabled).toBe(true)
    expect(host.querySelector('[data-testid="plan-fixed"]').textContent).toContain('Not offered for this facility’s level.')
  })

  it('works out a Custom amount and only lets a valid one be chosen', async () => {
    const host = document.createElement('div')
    document.body.append(host)
    await advanceToPricing(host, FACILITIES.slice(0, 1))
    const custom = host.querySelector('[data-testid="custom-package"]')
    await enterInput(custom.querySelector('#custom-amount'), '7000')
    expect(custom.textContent).toContain('1,166')
    expect(custom.textContent).toContain('KES 6,996.00')
    expect(custom.textContent).toContain('Starter rate · no first-purchase bonus')
    await enterInput(custom.querySelector('#custom-amount'), '5000')
    expect(custom.querySelector('.btn').disabled).toBe(true)
    await enterInput(custom.querySelector('#custom-amount'), '20000')
    custom.querySelector('.btn').click()
    await nextTick()
    expect(custom.textContent).toContain('3,731')
    expect(host.querySelector('.sumbar').textContent).toContain('KES 19,998')
    expect(sumbarButton(host).disabled).toBe(false)
  })

  it('preselects the plan carried from the landing page for every facility', async () => {
    window.history.replaceState(null, '', '/facility-onboarding?plan=fixed')
    vi.resetModules()
    const { default: Fresh } = await import('@/pages/FacilityOnboarding/FacilityOnboardingLanding.vue')
    const host = document.createElement('div')
    document.body.append(host)
    call
      .mockResolvedValueOnce({ message: { data: { session_token: 's', delivery: { status: 'sent', resend_after: 60 } } } })
      .mockResolvedValueOnce({ message: { data: { state: 'ready', identity: {}, account_email: 'owner@example.test', facilities: FACILITIES.slice(0, 2) } } })
      .mockResolvedValueOnce({ message: { data: { network: { name: 'NET-1' }, packages: FLEX, fixed_packages: FIXED, custom_offer: CUSTOM_OFFER } } })
    const app = createApp(Fresh)
    app.config.globalProperties.__ = globalThis.__
    app.mount(host)
    mountedApps.push(app)
    await enterInput(host.querySelector('input[placeholder="Enter your ID number"]'), '1')
    await submitForm(host.querySelector('form'))
    for (const [index, digit] of [...'123456'].entries()) {
      await enterInput(host.querySelectorAll('input[inputmode="numeric"]')[index], digit)
    }
    await submitForm(host.querySelector('form'))
    for (const cb of host.querySelectorAll('input[type="checkbox"]')) await checkInput(cb)
    await submitForm(host.querySelector('form'))
    await settle()
    expect(host.querySelector('[data-testid="carried-choice"]').textContent).toContain('Value Express Fixed')
    expect(host.querySelector('[data-testid="plan-fixed"]').getAttribute('aria-pressed')).toBe('true')
    expect(host.querySelector('.sumbar').textContent).toContain('2 of 2')
    expect(host.querySelector('.sumbar').textContent).toContain('KES 33,000')
  })
})
