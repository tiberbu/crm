import { createApp, nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

const call = vi.hoisted(() => vi.fn())
const coupons = vi.hoisted(() => ({ value: [] }))

vi.mock('frappe-ui', async () => {
  const { h } = await import('vue')
  const { default: dayjs } = await import('dayjs')
  const dayjsLocal = (d) => dayjs(d)
  const passthrough = (tag = 'div') => ({
    inheritAttrs: false,
    setup(_, { slots, attrs }) {
      return () => h(tag, attrs, slots.default?.())
    },
  })
  return {
    call,
    dayjsLocal,
    toast: { success: vi.fn(), error: vi.fn() },
    createResource: () => ({
      get data() {
        return { coupons: coupons.value }
      },
      loading: false,
      reload: vi.fn(),
    }),
    Badge: {
      props: ['label'],
      setup:
        (p, { attrs }) =>
        () =>
          h('span', attrs, p.label),
    },
    Button: passthrough('button'),
    Dialog: passthrough(),
    ErrorMessage: passthrough(),
    FormControl: passthrough(),
    LoadingIndicator: passthrough(),
    TabButtons: {
      props: ['buttons', 'modelValue'],
      emits: ['update:modelValue'],
      setup:
        (p, { emit, attrs }) =>
        () =>
          h(
            'div',
            attrs,
            p.buttons.map((b) =>
              h(
                'button',
                {
                  'data-tab': b.value,
                  onClick: () => emit('update:modelValue', b.value),
                },
                b.label,
              ),
            ),
          ),
    },
    TextInput: {
      props: ['modelValue'],
      emits: ['update:modelValue'],
      inheritAttrs: false,
      setup:
        (p, { emit, attrs }) =>
        () =>
          h('input', {
            'data-testid': attrs['data-testid'],
            value: p.modelValue,
            onInput: (e) => emit('update:modelValue', e.target.value),
          }),
    },
    Dropdown: {
      props: ['options'],
      setup: (p) => () =>
        h(
          'div',
          { 'data-testid': 'menu' },
          p.options.map((o) =>
            h(
              'button',
              { 'data-action': o.label, onClick: o.onClick },
              o.label,
            ),
          ),
        ),
    },
  }
})
vi.mock('@/components/Settings/CouponEditDialog.vue', () => ({
  default: { render: () => null },
}))
vi.mock('@/components/Settings/CouponRedemptions.vue', () => ({
  default: { render: () => null },
}))

import CouponManager from '@/components/Settings/CouponManager.vue'

const apps = []
afterEach(() => {
  apps.splice(0).forEach((app) => app.unmount())
  document.body.innerHTML = ''
  call.mockReset()
})

async function mount(rows) {
  window.sysdefaults = { ...window.sysdefaults, date_format: 'dd-mm-yyyy' }
  coupons.value = rows
  const el = document.createElement('div')
  document.body.appendChild(el)
  const app = createApp(CouponManager)
  app.config.globalProperties.__ = globalThis.__
  app.mount(el)
  apps.push(app)
  await nextTick()
  return el
}

const base = {
  value_type: 'flat_tokens',
  value: 100,
  redeemed_count: 0,
  created_by_name: 'Admin User',
  creation: '2026-11-01 10:00:00',
}
const ROWS = [
  {
    ...base,
    name: 'C1',
    coupon_title: 'North launch',
    network: 'north',
    network_name: 'Northern Partners',
    status: 'Inactive',
    derived_status: 'Inactive',
  },
  {
    ...base,
    name: 'C2',
    coupon_title: 'South launch',
    network: 'south',
    network_name: 'Southern Partners',
    status: 'Active',
    derived_status: 'Active',
  },
  {
    ...base,
    name: 'C3',
    coupon_title: 'Old promo',
    network: 'south',
    network_name: 'Southern Partners',
    status: 'Revoked',
    derived_status: 'Revoked',
    revoked_by_name: 'Ops Lead',
    revoked_on: '2026-11-05 09:00:00',
    revocation_reason: 'Ended early',
  },
]

const cards = (el) => [...el.querySelectorAll('[data-testid="coupon-card"]')]
const actionsOf = (card) =>
  [...card.querySelectorAll('[data-action]')].map((b) => b.dataset.action)

describe('CouponManager', () => {
  it('searches by partner network name', async () => {
    const el = await mount(ROWS)
    const input = el.querySelector('[data-testid="coupon-search"]')
    input.value = 'southern'
    input.dispatchEvent(new Event('input'))
    await nextTick()
    expect(cards(el).map((c) => c.dataset.coupon)).toEqual(['C2', 'C3'])
    expect(el.querySelector('[data-tab="Inactive"]').textContent).toBe(
      'Inactive (0)',
    )
  })

  it('shows the network name, creator and revocation details', async () => {
    const el = await mount(ROWS)
    const [inactive, , revoked] = cards(el)
    expect(inactive.textContent).toContain('Northern Partners')
    expect(
      inactive.querySelector('[data-testid="coupon-created"]').textContent,
    ).toContain('Admin User')
    expect(inactive.querySelector('[data-testid="coupon-revoked"]')).toBeNull()
    const revokedRow = revoked.querySelector('[data-testid="coupon-revoked"]')
    expect(revokedRow.textContent).toContain('Ops Lead')
    expect(revoked.textContent).toContain('Ended early')
  })

  it('offers enable, disable and revoke by status', async () => {
    const el = await mount(ROWS)
    const [inactive, active, revoked] = cards(el)
    expect(actionsOf(inactive)).toEqual([
      'Edit',
      'Redemptions',
      'Enable',
      'Revoke',
    ])
    expect(actionsOf(active)).toEqual([
      'Edit',
      'Redemptions',
      'Disable',
      'Revoke',
    ])
    expect(actionsOf(revoked)).toEqual(['Edit', 'Redemptions'])
  })

  it('enables an inactive coupon through the API', async () => {
    call.mockResolvedValue({})
    const el = await mount(ROWS)
    cards(el)[0].querySelector('[data-action="Enable"]').click()
    await nextTick()
    expect(call).toHaveBeenCalledWith('crm.api.coupons.enable_coupon', {
      name: 'C1',
    })
  })
})
