import { createApp, nextTick } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'

import OptInRequests from '@/pages/FacilityPortal/OptInRequests.vue'

const mountedApps = []

afterEach(() => {
  mountedApps.splice(0).forEach((app) => app.unmount())
  document.body.innerHTML = ''
})

describe('facility portal onboarding request distinction', () => {
  it('shows signatures only for invited Network Opt-In requests', async () => {
    const host = document.createElement('div')
    document.body.append(host)
    const app = createApp(OptInRequests, {
      requests: [
        {
          name: 'SELF-001',
          source: 'token_self_onboarding',
          network: 'Example Network',
          status: 'Processed',
          signatory: 'Self-Onboarding Contact',
          contract: 'CONTRACT-SELF',
          facilities: [],
          quotes: [],
          open_orders: 0,
          open_invoices: 0,
        },
        {
          name: 'OPTIN-001',
          source: 'network_optin',
          network: 'Example Network',
          status: 'Processed',
          signatory: 'Invited Signatory',
          contract: 'CONTRACT-OPTIN',
          facilities: [],
          quotes: [],
          open_orders: 0,
          open_invoices: 0,
        },
      ],
    })
    app.mount(host)
    mountedApps.push(app)
    await nextTick()

    expect(host.textContent).toContain('Requests & quotations')
    expect(host.textContent).toContain('Network Opt-In')
    expect(host.textContent).toContain('Invited Signatory')
    expect(host.textContent).not.toContain('Self-Onboarding Contact')
    expect(host.textContent).toContain('CONTRACT-OPTIN')
    expect(host.textContent).not.toContain('CONTRACT-SELF')
  })
})
