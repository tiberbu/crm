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

async function advanceToPricing(host, facilitiesList, packagesList) {
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
          identity: { full_name: 'Dr. John Doe' },
          account_email: 'john@example.com',
          facilities: facilitiesList,
        },
      },
    })
    .mockResolvedValueOnce({
      message: {
        data: {
          network: { name: 'NET-1', display_name: 'CareVerse Network' },
          packages: packagesList,
        },
      },
    })

  const app = createApp(FacilityOnboardingLanding)
  app.config.globalProperties.__ = (text, args) =>
    args ? text.replace(/:(\w+)/g, (_, k) => args[k]) : text
  app.mount(host)
  mountedApps.push(app)

  // Start onboarding
  const startBtn = [...host.querySelectorAll('button')].find((b) =>
    b.textContent.includes('Start secure onboarding'),
  )
  startBtn.click()
  await nextTick()

  // Submit identity
  const idInput = host.querySelector('input[placeholder="Enter your ID number"]')
  await enterInput(idInput, '12345678')
  await submitForm(host.querySelector('form'))

  // Submit OTP
  for (const [index, digit] of [...'123456'].entries()) {
    const input = host.querySelectorAll('input[inputmode="numeric"]')[index]
    await enterInput(input, digit)
  }
  await submitForm(host.querySelector('form'))

  // Select facilities
  const checkboxes = host.querySelectorAll('input[type="checkbox"]')
  for (const cb of checkboxes) {
    if (!cb.disabled) {
      await checkInput(cb)
    }
  }
  await submitForm(host.querySelector('form'))
  await settle()
}

describe('Pricing Stage UX Audit & Minimalist Experience', () => {
  const standardPackages = [
    {
      item_code: 'CV-TOKEN-FREE',
      display_name: 'Free Trial',
      rate: 0,
      price_ex_vat: 0,
      token_quantity: 400,
      currency: 'KES',
    },
    {
      item_code: 'CV-TOKEN-STARTER',
      display_name: 'Starter',
      rate: 6000,
      price_ex_vat: 6000,
      token_quantity: 1000,
      currency: 'KES',
    },
    {
      item_code: 'CV-TOKEN-GROWTH',
      display_name: 'Growth',
      rate: 15000,
      price_ex_vat: 15000,
      token_quantity: 2800,
      currency: 'KES',
    },
    {
      item_code: 'CV-TOKEN-SCALE',
      display_name: 'Scale',
      rate: 30000,
      price_ex_vat: 30000,
      token_quantity: 6250,
      currency: 'KES',
    },
  ]

  it('renders single facility context pill when 1 facility is selected', async () => {
    const host = document.createElement('div')
    document.body.append(host)

    await advanceToPricing(
      host,
      [
        {
          facility_id: 'FID-1',
          facility_name: 'Nairobi West Clinic',
          mfl_code: '10234',
          classification: 'Level 3',
          onboarding_eligible: true,
        },
      ],
      standardPackages,
    )

    expect(host.textContent).toContain('Nairobi West Clinic')
    expect(host.textContent).toContain('Level 3')
    expect(host.textContent).toContain('MFL 10234')
    // Tabs should NOT be rendered when only 1 facility is selected
    expect(host.querySelector('[role="tablist"]')).toBeNull()
  })

  it('renders multi-facility tabs and enables fast switching between clinics', async () => {
    const host = document.createElement('div')
    document.body.append(host)

    await advanceToPricing(
      host,
      [
        {
          facility_id: 'FID-1',
          facility_name: 'Alpha Health Center',
          mfl_code: '101',
          classification: 'Level 3',
          onboarding_eligible: true,
        },
        {
          facility_id: 'FID-2',
          facility_name: 'Beta Dispensary',
          mfl_code: '102',
          classification: 'Level 2',
          onboarding_eligible: true,
        },
      ],
      standardPackages,
    )

    // Facility Tab bar should be visible
    const tablist = host.querySelector('[role="tablist"]')
    expect(tablist).toBeTruthy()
    const tabs = tablist.querySelectorAll('[role="tab"]')
    expect(tabs).toHaveLength(2)
    expect(tabs[0].textContent).toContain('Alpha Health Center')
    expect(tabs[1].textContent).toContain('Beta Dispensary')

    // At-A-Glance summary table should be present
    expect(host.textContent).toContain('Facility Package Allocation')
    expect(host.textContent).toContain('2 facilities')

    // Click on Growth plan for Alpha
    const growthArticle = [...host.querySelectorAll('article')].find((a) =>
      a.textContent.includes('Growth'),
    )
    growthArticle.click()
    await nextTick()

    // Alpha tab should reflect selected plan
    expect(tabs[0].textContent).toContain('Growth')

    // Switch to Beta Dispensary tab
    tabs[1].click()
    await nextTick()

    // Now Beta is active; select Free Trial for Beta
    const freeArticle = [...host.querySelectorAll('article')].find((a) =>
      a.textContent.includes('Free Trial'),
    )
    freeArticle.click()
    await nextTick()

    expect(tabs[1].textContent).toContain('Free Trial')
  })

  it('provides "Apply plan to all facilities" button that configures all clinics at once', async () => {
    const host = document.createElement('div')
    document.body.append(host)

    await advanceToPricing(
      host,
      [
        {
          facility_id: 'FID-1',
          facility_name: 'Alpha Health Center',
          onboarding_eligible: true,
        },
        {
          facility_id: 'FID-2',
          facility_name: 'Beta Dispensary',
          onboarding_eligible: true,
        },
        {
          facility_id: 'FID-3',
          facility_name: 'Gamma Medical',
          onboarding_eligible: true,
        },
      ],
      standardPackages,
    )

    // Select Scale plan on current facility (Alpha)
    const scaleArticle = [...host.querySelectorAll('article')].find((a) =>
      a.textContent.includes('Scale'),
    )
    scaleArticle.click()
    await nextTick()

    // Find and click "Apply plan to all 3 facilities"
    const applyAllBtn = [...host.querySelectorAll('button')].find((b) =>
      b.textContent.includes('Apply plan to all 3 facilities'),
    )
    expect(applyAllBtn).toBeTruthy()
    applyAllBtn.click()
    await nextTick()

    // All 3 tabs should now have Scale
    const tabs = host.querySelectorAll('[role="tab"]')
    expect(tabs[0].textContent).toContain('Scale')
    expect(tabs[1].textContent).toContain('Scale')
    expect(tabs[2].textContent).toContain('Scale')

    // Form continue button should now be enabled
    const submitBtn = host.querySelector('button:not([type="button"])')
    expect(submitBtn.disabled).toBe(false)
  })

  it('opens TokenCalculator in a clean modal dialog when clicking trigger banner', async () => {
    const host = document.createElement('div')
    document.body.append(host)

    await advanceToPricing(
      host,
      [
        {
          facility_id: 'FID-1',
          facility_name: 'Nairobi Clinic',
          onboarding_eligible: true,
        },
      ],
      standardPackages,
    )

    // Initially modal is not open
    expect(host.querySelector('[role="dialog"]')).toBeNull()

    // Trigger button should be visible
    const calcTrigger = [...host.querySelectorAll('button')].find((b) =>
      b.textContent.includes('Open Sizing Calculator'),
    )
    expect(calcTrigger).toBeTruthy()
    calcTrigger.click()
    await nextTick()

    // Modal dialog should now be rendered
    const dialog = host.querySelector('[role="dialog"]')
    expect(dialog).toBeTruthy()
    expect(dialog.getAttribute('aria-label')).toContain('CareVerse Token Sizing Calculator')
    expect(dialog.querySelector('[data-testid="token-calculator"]')).toBeTruthy()
  })

  it('renders all 4 packages symmetrically with consistent KES pricing and no un-interpolated tokens', async () => {
    const host = document.createElement('div')
    document.body.append(host)

    await advanceToPricing(
      host,
      [
        {
          facility_id: 'FID-1',
          facility_name: 'Nairobi Clinic',
          onboarding_eligible: true,
        },
      ],
      standardPackages,
    )

    const articles = host.querySelectorAll('article')
    expect(articles).toHaveLength(4)

    // Check consistent KES currency formatting across cards
    expect(articles[0].textContent).toContain('KES 0')
    expect(articles[1].textContent).toContain('KES 6,000')
    expect(articles[2].textContent).toContain('KES 15,000')
    expect(articles[3].textContent).toContain('KES 30,000')

    // Ensure no un-interpolated :n or raw placeholders exist in DOM
    expect(host.textContent).not.toContain(':n')

    // Ensure section expands with w-full when on pricing stage
    const section = host.querySelector('form[data-testid="facility-package-FID-1"]')?.closest('section') || host.querySelector('section')
    expect(section?.classList.contains('w-full')).toBe(true)
  })
})

