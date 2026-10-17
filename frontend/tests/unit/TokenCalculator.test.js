import { createApp, nextTick } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'
import TokenCalculator from '@/components/TokenCalculator.vue'

const mountedApps = []

afterEach(() => {
  mountedApps.splice(0).forEach((app) => app.unmount())
  document.body.innerHTML = ''
})

function mountCalculator(props = {}) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const app = createApp(TokenCalculator, {
    packages: [
      {
        item_code: 'CV-TOKEN-STARTER',
        display_name: 'Starter',
        token_quantity: 1000,
        price: 6096,
        price_ex_vat: 6096,
        gross_total: 7071.36,
        currency: 'KES',
      },
      {
        item_code: 'CV-TOKEN-GROWTH',
        display_name: 'Growth',
        token_quantity: 2500,
        price: 13970,
        price_ex_vat: 13970,
        gross_total: 16205.2,
        currency: 'KES',
      },
      {
        item_code: 'CV-TOKEN-SCALE',
        display_name: 'Scale',
        token_quantity: 5000,
        price: 25400,
        price_ex_vat: 25400,
        gross_total: 29464,
        currency: 'KES',
      },
    ],
    ...props,
  })
  app.mount(container)
  mountedApps.push(app)
  return container
}

describe('TokenCalculator.vue', () => {
  it('renders the interactive token calculator with default preset', () => {
    const el = mountCalculator({ facilityName: 'St. Mary Dispensary' })
    expect(el.querySelector('[data-testid="token-calculator"]')).toBeTruthy()
    expect(el.textContent).toContain('St. Mary Dispensary')
    expect(el.textContent).toContain('Interactive Token Sizing Calculator')
    expect(el.textContent).toContain('Projected Monthly Demand')
    expect(el.querySelector('[data-testid="recommended-package-card"]')).toBeTruthy()
  })

  it('adjusts calculations when clicking presets', async () => {
    const el = mountCalculator()
    const soloPresetBtn = Array.from(el.querySelectorAll('button')).find((b) =>
      b.textContent.includes('Solo Practice / Clinic'),
    )
    expect(soloPresetBtn).toBeTruthy()

    soloPresetBtn.click()
    await nextTick()

    // Solo preset has 5 pts/day, OPD, avg bill 1500, 24 days
    // 5 * 24 = 120 encounters
    expect(el.textContent).toContain('~120 encounters')
    // Recommendation for solo should be Starter
    expect(el.querySelector('[data-testid="recommended-package-card"]').textContent).toContain(
      'Starter',
    )
  })

  it('recommends Growth package for active outpatient volume', async () => {
    const el = mountCalculator()
    const activePresetBtn = Array.from(el.querySelectorAll('button')).find((b) =>
      b.textContent.includes('Active Outpatient Clinic'),
    )
    activePresetBtn.click()
    await nextTick()

    // 10 pts/day, 24 days = 240 encounters
    expect(el.textContent).toContain('~240 encounters')
    // Should recommend Growth (2500 tokens)
    const recCard = el.querySelector('[data-testid="recommended-package-card"]')
    expect(recCard.textContent).toContain('Growth')
    expect(recCard.textContent).toContain('2,500 Tokens')
  })

  it('recommends Scale package for hospital preset', async () => {
    const el = mountCalculator()
    const hospitalPresetBtn = Array.from(el.querySelectorAll('button')).find((b) =>
      b.textContent.includes('Medical Center / Hospital'),
    )
    hospitalPresetBtn.click()
    await nextTick()

    // 25 pts/day, IPD, avg bill 2500, 24 days = 600 encounters
    expect(el.textContent).toContain('~600 encounters')
    const recCard = el.querySelector('[data-testid="recommended-package-card"]')
    expect(recCard.textContent).toContain('Scale')
    expect(recCard.textContent).toContain('5,000 Tokens')
  })

  it('emits select-package and apply-plan when user selects a plan', async () => {
    let selectedCode = ''
    let appliedPlan = null
    const el = mountCalculator({
      onSelectPackage: (code) => {
        selectedCode = code
      },
      onApplyPlan: (pkg) => {
        appliedPlan = pkg
      },
    })

    const selectBtn = el.querySelector('[data-testid="recommended-package-card"] button')
    expect(selectBtn).toBeTruthy()
    selectBtn.click()
    await nextTick()

    expect(selectedCode).toBeTruthy()
    expect(appliedPlan).toBeTruthy()
    expect(appliedPlan.item_code).toBe(selectedCode)
  })

  it('respects custom settings passed in config prop', async () => {
    const el = mountCalculator({
      config: {
        monthly_platform_fee: 1000,
        bill_value_per_token: 500,
        default_avg_bill: 2000,
        default_operating_days: 26,
      },
    })

    // At bill 2000 and ratio 500 => ceil(2000/500) = 4 bill tokens
    expect(el.textContent).toContain('1000 🪙')
  })

  it('supports context="landing" with start-onboarding CTA button and link', async () => {
    let startedPlan = null
    const el = mountCalculator({
      context: 'landing',
      onStartOnboarding: (pkg) => {
        startedPlan = pkg
      },
    })

    const ctaBtn = el.querySelector('[data-testid="recommended-package-card"] button')
    expect(ctaBtn).toBeTruthy()
    expect(ctaBtn.textContent).toContain('Start onboarding with')

    ctaBtn.click()
    await nextTick()

    expect(startedPlan).toBeTruthy()
    expect(startedPlan.item_code).toBe('CV-TOKEN-SCALE')
  })

  it('toggles collapsible fine-tune drawer for clinical mix', async () => {
    const el = mountCalculator()
    const toggleBtn = Array.from(el.querySelectorAll('button')).find((b) =>
      b.textContent.includes('Fine-tune Clinical Assumptions & Mix'),
    )
    expect(toggleBtn).toBeTruthy()

    // Initially collapsed
    expect(toggleBtn.textContent).toContain('Customize')

    // Click to expand
    toggleBtn.click()
    await nextTick()
    expect(toggleBtn.textContent).toContain('Hide')

    // Click again to collapse
    toggleBtn.click()
    await nextTick()
    expect(toggleBtn.textContent).toContain('Customize')
  })

  it('uses standard fallback packages when packages prop is empty', async () => {
    const el = mountCalculator({ packages: [] })
    const recCard = el.querySelector('[data-testid="recommended-package-card"]')
    expect(recCard).toBeTruthy()
    expect(recCard.textContent).toContain('Scale')
    expect(recCard.textContent).toContain('5,000 Tokens')

    // Clicking solo preset switches recommendation to Starter
    const soloBtn = Array.from(el.querySelectorAll('button')).find((b) =>
      b.textContent.includes('Solo Practice / Clinic'),
    )
    soloBtn.click()
    await nextTick()

    expect(recCard.textContent).toContain('Starter')
    expect(recCard.textContent).toContain('1,000 Tokens')
  })
})

