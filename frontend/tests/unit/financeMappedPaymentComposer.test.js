import { createApp, h, nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Invoices from '../../src/pages/FinanceCockpit/sections/Invoices.vue'

const mappedPayment = {
  doctype: 'Payment Entry',
  payment_type: 'Receive',
  party_type: 'Customer',
  party: 'CUST-001',
  company: 'Careverse HQ',
  posting_date: '2026-10-12',
  mode_of_payment: 'Bank Transfer',
  reference_no: 'BANK-REF-001',
  reference_date: '2026-10-12',
  paid_from_account_currency: 'KES',
  references: [
    {
      reference_doctype: 'Sales Invoice',
      reference_name: 'SINV-001',
      allocated_amount: 1250,
    },
  ],
}

vi.mock('frappe-ui', async () => {
  const { defineComponent, h, ref } = await import('vue')
  const Button = defineComponent({
    inheritAttrs: false,
    props: { label: String, disabled: Boolean },
    setup(props, { attrs, slots }) {
      return () =>
        h(
          'button',
          { ...attrs, disabled: props.disabled },
          slots.default?.() || props.label,
        )
    },
  })
  return {
    Button,
    Breadcrumbs: defineComponent({ render: () => h('nav') }),
    ListView: defineComponent({ render: () => h('div') }),
    FormControl: defineComponent({
      props: { label: String, modelValue: String },
      setup(props) {
        return () => h('input', { type: 'text', value: props.modelValue })
      },
    }),
    Combobox: defineComponent({ render: () => h('div') }),
    DatePicker: defineComponent({
      props: { modelValue: String },
      setup(props) {
        return () => h('input', { type: 'date', value: props.modelValue })
      },
    }),
    createResource({ url }) {
      return {
        fetch: async () =>
          url === 'crm.finance.api.get_ar_invoices'
            ? [
                {
                  name: 'SINV-001',
                  customer: 'CUST-001',
                  outstanding_amount: 1250,
                  currency: 'KES',
                },
              ]
            : [],
        submit: async () => {
          if (url === 'crm.finance.api.get_customer_outstanding_invoices') {
            return [
              {
                name: 'SINV-001',
                outstanding_amount: 1250,
                currency: 'KES',
                due_date: '2026-10-01',
              },
              {
                name: 'SINV-OTHER',
                outstanding_amount: 300,
                currency: 'KES',
                due_date: '2026-10-02',
              },
            ]
          }
          if (url === 'crm.finance.api.get_customer_payment_context') {
            return {
              configured: true,
              account: 'Bank - CV',
              account_type: 'Bank',
              requires_reference: true,
            }
          }
          if (url === 'frappe.client.get_list') return [{ name: 'Cash' }]
          return []
        },
      }
    },
    debounce: (fn) => fn,
    toast: { success() {}, error() {} },
    ref,
  }
})

vi.mock('../../src/pages/FinanceCockpit/composables/useCompanyContext.js', async () => {
  const { ref } = await import('vue')
  const company = ref('Careverse HQ')
  return { useCompanyContext: () => ({ company }) }
})
vi.mock('../../src/pages/FinanceCockpit/composables/useCurrency.js', () => ({
  useCurrency: () => ({
    formatCurrency: (amount, currency) => `${currency || ''} ${amount}`.trim(),
  }),
}))
vi.mock('../../src/pages/FinanceCockpit/composables/useBreakpoint.js', async () => {
  const { ref } = await import('vue')
  return { useBreakpoint: () => ({ isMobile: ref(true) }) }
})
vi.mock('../../src/pages/FinanceCockpit/composables/useBoot.js', () => ({
  useBoot: () => ({
    getRoles: () => ['Accounts User'],
    isAdministrator: () => false,
  }),
}))
vi.mock('../../src/pages/FinanceCockpit/composables/financeErrors.js', () => ({
  readableError: (error) => String(error),
}))

vi.mock('../../src/pages/FinanceCockpit/components/crud/FinanceDetail.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    default: defineComponent({
      emits: ['mapped'],
      setup(_props, { emit }) {
        return () =>
          h(
            'button',
            { onClick: () => emit('mapped', mappedPayment) },
            'Map invoice payment',
          )
      },
    }),
  }
})
vi.mock('../../src/pages/FinanceCockpit/components/crud/FinanceForm.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return { default: defineComponent({ render: () => h('div') }) }
})
vi.mock('../../src/pages/FinanceCockpit/components/crud/CreateFromPicker.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    default: defineComponent({
      emits: ['mapped'],
      setup(_props, { emit }) {
        return () =>
          h(
            'button',
            { onClick: () => emit('mapped', mappedPayment) },
            'Map selected invoice',
          )
      },
    }),
  }
})
vi.mock('../../src/pages/FinanceCockpit/components/crud/FcIcon.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return { default: defineComponent({ render: () => h('span') }) }
})
vi.mock('../../src/pages/FinanceCockpit/components/crud/StatusBadge.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return { default: defineComponent({ render: () => h('span') }) }
})
vi.mock('../../src/pages/FinanceCockpit/components/FinanceErrorState.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return { default: defineComponent({ render: () => h('div') }) }
})
vi.mock('../../src/pages/FinanceCockpit/components/crud/SectionCard.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    default: defineComponent({
      props: { title: String },
      setup(props, { slots }) {
        return () => h('section', [h('h3', props.title), slots.default?.()])
      },
    }),
  }
})

let app
let host

afterEach(() => {
  app?.unmount()
  host?.remove()
  app = null
  host = null
})

async function settle() {
  for (let i = 0; i < 8; i += 1) await Promise.resolve()
  await nextTick()
}

describe('invoice-mapped payment composer', () => {
  it('opens from the invoice section with editable amount and only the mapped invoice', async () => {
    host = document.createElement('div')
    document.body.append(host)
    app = createApp(Invoices)
    app.mount(host)
    await settle()

    const invoiceRow = [...host.querySelectorAll('button')].find((button) =>
      button.textContent.includes('SINV-001'),
    )
    expect(invoiceRow).toBeTruthy()
    invoiceRow.click()
    await settle()

    const mapPayment = [...host.querySelectorAll('button')].find((button) =>
      button.textContent.includes('Map invoice payment'),
    )
    expect(mapPayment).toBeTruthy()
    mapPayment.click()
    await settle()

    expect(host.textContent).toContain('Create Invoice Payment')
    expect(host.textContent).toContain('CUST-001')
    expect(host.textContent).toContain('SINV-001')
    expect(host.textContent).not.toContain('SINV-OTHER')

    const amountInputs = [...host.querySelectorAll('input[type="number"]')]
    expect(amountInputs).toHaveLength(2)
    expect(amountInputs[0].value).toBe('1250')
    expect(amountInputs[0].disabled).toBe(false)
    expect(amountInputs[1].value).toBe('1250')
    expect(amountInputs[1].disabled).toBe(false)
    expect(host.querySelector('input[type="text"]').value).toBe('BANK-REF-001')
    expect(host.querySelector('input[type="date"]').value).toBe('2026-10-12')

    amountInputs[1].value = '500'
    amountInputs[1].dispatchEvent(new Event('input', { bubbles: true }))
    await settle()
    expect(amountInputs[1].value).toBe('500')
  })
})
