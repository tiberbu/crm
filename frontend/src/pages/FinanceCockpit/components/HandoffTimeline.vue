<template>
  <section class="fc-glass-card !p-0 overflow-hidden" aria-labelledby="handoff-title">
    <div class="px-5 pt-4 pb-3 border-b border-outline-gray-1/60 flex items-start justify-between gap-3">
      <div>
        <h3 id="handoff-title" class="text-sm font-semibold text-ink-gray-8">
          Signed facility handoffs
        </h3>
        <p class="text-xs text-ink-gray-5 mt-0.5">
          Year 1 quotation → Q1 order → invoice, using the live accounting records.
        </p>
      </div>
      <button
        type="button"
        class="text-xs font-medium text-ink-red-6 hover:text-ink-red-8 disabled:opacity-50"
        :disabled="resource.loading"
        aria-label="Refresh signed facility handoffs"
        @click="refresh"
      >
        Refresh
      </button>
    </div>

    <div v-if="resource.loading" class="p-5 space-y-3" aria-live="polite">
      <div v-for="n in 2" :key="n" class="h-28 rounded-lg bg-surface-gray-2 animate-pulse" />
    </div>

    <FinanceErrorState v-else-if="resource.error" :error="resource.error" @retry="refresh" />

    <div v-else-if="!handoffs.length" class="p-8 text-center text-sm text-ink-gray-4">
      No signed facility handoffs are waiting for finance action.
    </div>

    <ol v-else class="divide-y divide-outline-gray-1/50">
      <li v-for="handoff in handoffs" :key="handoff.submission" class="p-5">
        <div class="flex items-start gap-3">
          <span
            class="mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-surface-red-2 text-xs font-semibold text-ink-red-6"
            aria-hidden="true"
          >
            {{ handoff.network ? handoff.network.slice(0, 1).toUpperCase() : 'F' }}
          </span>
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h4 class="font-medium text-ink-gray-8 truncate">
                  {{ handoff.network || 'Signed facility' }}
                </h4>
                <p class="mt-0.5 text-xs text-ink-gray-5">
                  Signed {{ formatDateTime(handoff.contract?.signed_at || handoff.submitted_at) }}
                  <span v-if="handoff.owner"> · Created by {{ ownerLabel(handoff.owner) }}</span>
                </p>
              </div>
              <span class="rounded-full bg-surface-amber-2 px-2 py-1 text-xs font-medium text-ink-amber-7">
                {{ handoff.next_step }}
              </span>
            </div>

            <div class="mt-4 grid gap-2 sm:grid-cols-4">
              <div
                v-for="step in steps(handoff)"
                :key="step.key"
                class="rounded-lg border border-outline-gray-1 bg-surface-gray-1/50 p-3"
              >
                <button
                  type="button"
                  class="w-full text-left focus:outline-none focus:ring-2 focus:ring-outline-blue-3 rounded"
                  :aria-label="`${step.label}: ${step.name || 'not generated'}`"
                  @click="$emit('navigate', step.section)"
                >
                  <span class="block text-[11px] font-medium uppercase tracking-wide text-ink-gray-5">
                    {{ step.label }}
                  </span>
                  <span class="mt-1 block truncate text-sm font-medium text-ink-gray-8">
                    {{ step.name || 'Not generated' }}
                  </span>
                  <span class="mt-1 block truncate text-xs text-ink-gray-5">
                    {{ step.state }}
                  </span>
                </button>
                <a
                  v-if="step.name"
                  :href="nativeHref(step)"
                  target="_blank"
                  rel="noopener"
                  class="mt-2 inline-block text-[11px] font-medium text-ink-gray-6 underline underline-offset-2 hover:text-ink-gray-9"
                  @click.stop
                >
                  Open record
                </a>
              </div>
            </div>

            <p
              v-if="handoff.schedule?.error || handoff.schedule?.handoff_note"
              class="mt-3 rounded-md bg-surface-amber-1 px-3 py-2 text-xs text-ink-amber-8"
              role="note"
            >
              {{ handoff.schedule.error || handoff.schedule.handoff_note }}
            </p>
            <p class="mt-3 text-[11px] text-ink-gray-4">
              Last modified {{ formatDateTime(handoff.modified) }}
            </p>
          </div>
        </div>
      </li>
    </ol>
  </section>
</template>

<script setup>
import { computed, watch } from 'vue'
import { createResource } from 'frappe-ui'
import { useCompanyContext } from '../composables/useCompanyContext.js'
import FinanceErrorState from './FinanceErrorState.vue'

defineEmits(['navigate'])
const { company } = useCompanyContext()

const resource = createResource({
  url: 'crm.finance.api.get_signed_handoff_timeline',
  makeParams() {
    return { company: company.value, page: 0, page_size: 8 }
  },
  auto: true,
})

const handoffs = computed(() => resource.data || [])

function refresh() {
  resource.fetch()
}

watch(company, refresh)

function ownerLabel(owner) {
  return owner ? String(owner).split('@')[0] : '—'
}

function formatDateTime(value) {
  if (!value) return 'date not available'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function nativeState(doc) {
  if (!doc) return 'Not generated'
  if (doc.status) return doc.status
  return Number(doc.docstatus) === 1 ? 'Submitted' : 'Draft'
}

function nativeHref(step) {
  const routes = {
    quotation: 'quotation',
    sales_order: 'sales-order',
    sales_invoice: 'sales-invoice',
    payment: 'payment-entry',
  }
  return `/app/${routes[step.key]}/${encodeURIComponent(step.name)}`
}

function steps(handoff) {
  return [
    {
      key: 'quotation',
      label: 'Year 1 quotation',
      name: handoff.quotation?.name,
      state: nativeState(handoff.quotation),
      section: 'quotes',
    },
    {
      key: 'sales_order',
      label: 'Q1 sales order',
      name: handoff.sales_order?.name,
      state: nativeState(handoff.sales_order),
      section: 'orders',
    },
    {
      key: 'sales_invoice',
      label: 'Sales invoice',
      name: handoff.sales_invoice?.name,
      state: nativeState(handoff.sales_invoice),
      section: 'invoices',
    },
    {
      key: 'payment',
      label: 'Payment entries',
      name: handoff.payments?.[0]?.name || '',
      state: handoff.payments?.length
        ? `${handoff.payments.length} recorded`
        : handoff.sales_invoice
          ? 'Process from Invoices'
          : 'After invoice submission',
      section: 'payments',
    },
  ]
}
</script>
