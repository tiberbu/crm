import { createApp, nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import StepLanding from '@/pages/OptIn/StepLanding.vue'

const mountedApps = []

afterEach(() => {
  mountedApps.splice(0).forEach((app) => app.unmount())
  document.body.innerHTML = ''
})

describe('Opt-In invitation landing', () => {
  it('explains network eligibility and continues the invited user into the flow', async () => {
    const host = document.createElement('div')
    document.body.append(host)
    const onNext = vi.fn()
    const app = createApp(StepLanding, {
      networkConfig: { display_name: 'Example Health Network' },
      onNext,
    })
    app.mount(host)
    mountedApps.push(app)
    await nextTick()

    expect(host.textContent).toContain('Example Health Network')
    expect(host.textContent).toContain('facilities added to this network')
    expect(host.textContent).toContain('email address linked to it')
    expect(host.textContent).toContain('quotation and agreement')

    const continueButton = [...host.querySelectorAll('button')].find((button) =>
      button.textContent.includes('Continue with Opt-In'),
    )
    expect(continueButton).toBeTruthy()
    continueButton.click()
    expect(onNext).toHaveBeenCalledTimes(1)
  })
})
