import { createApp, nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

// The ledger loads over the network; these tests cover the request card itself.
vi.mock('frappe-ui', () => ({ call: vi.fn(() => new Promise(() => {})) }))

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

  it('names the partner network, never the network record', async () => {
    const host = document.createElement('div')
    document.body.append(host)
    const app = createApp(OptInRequests, {
      requests: [
        {
          name: 'OPTIN-002',
          source: '',
          network: 'Example Partner Network',
          status: 'Submitted',
          facilities: [],
          quotes: ['SAL-QTN-1', 'SAL-QTN-2'],
          open_orders: 0,
          open_invoices: 0,
        },
      ],
    })
    app.mount(host)
    mountedApps.push(app)
    await nextTick()
    expect(host.textContent).toContain('Example Partner Network')
    expect(host.textContent).not.toContain('[object Object]')
    // Quotes are a list, not one joined string.
    expect(host.querySelectorAll('li').length).toBe(2)
  })
})
