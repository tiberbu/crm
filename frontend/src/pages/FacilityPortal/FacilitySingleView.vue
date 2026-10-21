<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import CxIcon from './components/CxIcon.vue'

const props = defineProps({
  facility: { type: Object, required: true },
  invoices: { type: Array, default: () => [] },
  orders: { type: Array, default: () => [] },
  payments: { type: Array, default: () => [] },
  defaultCurrency: { type: String, default: 'KES' },
  loadProvisioningStatus: { type: Function, required: true },
})
const emit = defineEmits(['back', 'open-top-up', 'pay'])
const provisioning = ref(null)
const provisioningBusy = ref(false)
const provisioningError = ref('')

async function loadStatus() {
  provisioningBusy.value = true
  provisioningError.value = ''
  try {
    provisioning.value = await props.loadProvisioningStatus(props.facility.mfl_code)
  } catch (error) {
    provisioningError.value = error?.messages?.[0] || 'Implementation status could not be loaded.'
  } finally {
    provisioningBusy.value = false
  }
}
onMounted(loadStatus)
watch(() => props.facility.mfl_code, loadStatus)

const statusLabel = computed(() => {
  const status = String(provisioning.value?.status || '').toLowerCase()
  if (status === 'deployed') return 'Live'
  if (status === 'draft') return 'Draft ready for review'
  if (status === 'not_submitted') return 'Setup not started'
  if (status.includes('error') || provisioning.value?.has_error) return 'Needs attention'
  if (status === 'not_configured') return 'Tracking not connected'
  if (status === 'route_not_provisioned') return 'Tracking not available yet'
  if (status === 'needs_support') return 'Needs implementation support'
  if (status === 'unavailable') return 'Status unavailable'
  return provisioning.value?.status || 'Not started'
})

const statusTone = computed(() => {
  const status = String(provisioning.value?.status || '').toLowerCase()
  if (status === 'deployed') return 'border-cx-success-border bg-cx-success-soft text-cx-success-ink'
  if (status === 'draft' || status === 'not_submitted') return 'border-cx-warning-border bg-cx-warning-soft text-cx-warning-ink'
  if (status.includes('error') || status === 'needs_support' || provisioning.value?.has_error) return 'border-cx-danger-border bg-cx-danger-soft text-cx-danger-ink'
  return 'border-cx-border bg-cx-well text-cx-ink-2'
})

const statusGuidance = computed(() => {
  const status = String(provisioning.value?.status || '').toLowerCase()
  if (status === 'draft') return 'A setup record exists. The implementation team must review it and start deployment from the setup tool.'
  if (status === 'deployed') return 'The implementation service reports this facility as deployed.'
  if (status === 'not_submitted') return 'There is no setup record for this facility yet. Contact your implementation team to begin setup.'
  if (status.includes('error') || provisioning.value?.has_error) return 'The implementation team needs to review the latest deployment attempt.'
  return provisioning.value?.message || (provisioningBusy.value ? 'Checking the implementation service…' : 'Implementation status has not been checked.')
})

const progressValue = computed(() => {
  if (provisioning.value?.progress == null || provisioning.value?.progress === '') return null
  const value = Number(provisioning.value?.progress)
  return Number.isFinite(value) ? Math.min(100, Math.max(0, Math.round(value))) : null
})

const statusSource = computed(() => provisioning.value?.source === 'external_setup' ? 'Setup service' : provisioning.value?.source === 'hie_gateway' ? 'HIE gateway' : 'Status source pending')

function money(amount, currency) {
  return new Intl.NumberFormat('en-KE', { style: 'currency', currency: currency || props.defaultCurrency, maximumFractionDigits: 0 }).format(amount || 0)
}

function invoiceStatus(invoice) {
  return invoice.status || 'Outstanding'
}

function pendingPaymentForInvoice(invoice) {
  return props.payments.find((payment) => {
    if (payment.status !== 'Pending Verification') return false
    const invoiceNames = payment.invoice_names?.length
      ? payment.invoice_names
      : payment.invoice
        ? [payment.invoice]
        : []
    return invoiceNames.some((name) => String(name) === String(invoice.name))
  }) || null
}
</script>

<template>
  <section class="mx-auto w-full max-w-6xl space-y-6 pb-8">
    <div class="flex flex-wrap items-center justify-between gap-4">
      <div>
        <button type="button" class="mb-3 inline-flex items-center gap-2 text-xs font-semibold text-cx-brand hover:underline" @click="emit('back')">
          <CxIcon name="chevron-left" class="size-4" /> Back to facilities
        </button>
        <p class="text-[11px] font-semibold uppercase tracking-[0.12em] text-cx-ink-3">Facility portfolio</p>
        <h1 class="mt-1 text-3xl font-bold tracking-tight text-cx-ink">{{ facility.facility_name }}</h1>
        <p class="mt-1 text-sm text-cx-ink-3">{{ facility.keph_level }} <span v-if="facility.county">· {{ facility.county }}</span></p>
      </div>
      <button type="button" class="rounded-cx-sm bg-cx-brand px-4 py-2.5 text-xs font-semibold text-cx-contrast shadow-cx hover:bg-cx-brand-strong" @click="emit('open-top-up', facility)">
        Top up tokens
      </button>
    </div>

    <section class="overflow-hidden rounded-cx border border-cx-border bg-cx-surface shadow-cx">
      <div class="border-b border-cx-border-soft bg-gradient-to-br from-cx-surface via-cx-surface to-cx-well/70 p-5 sm:p-7">
        <div class="flex flex-wrap items-start justify-between gap-5">
          <div class="max-w-3xl">
            <p class="text-[11px] font-semibold uppercase tracking-[0.12em] text-cx-ink-3">Implementation</p>
            <div class="mt-2 flex flex-wrap items-center gap-3">
              <h2 class="text-2xl font-bold tracking-tight text-cx-ink">HMIS implementation</h2>
              <span class="inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold" :class="statusTone">{{ statusLabel }}</span>
            </div>
            <p class="mt-2 max-w-2xl text-sm leading-relaxed text-cx-ink-2">{{ statusGuidance }}</p>
          </div>
          <button type="button" class="rounded-cx-sm border border-cx-border bg-cx-surface px-3 py-2 text-xs font-semibold text-cx-ink-2 shadow-sm hover:bg-cx-well disabled:opacity-50" :disabled="provisioningBusy" @click="loadStatus">
            {{ provisioningBusy ? 'Refreshing…' : 'Refresh status' }}
          </button>
        </div>
        <p v-if="provisioningError" class="mt-4 rounded-cx-sm border border-cx-danger-border bg-cx-danger-soft px-3 py-2 text-xs text-cx-danger-ink" role="alert">{{ provisioningError }}</p>
        <div v-if="progressValue != null" class="mt-6 max-w-3xl">
          <div class="mb-2 flex items-center justify-between text-xs"><span class="font-semibold text-cx-ink-2">Reported deployment progress</span><strong class="text-sm text-cx-ink">{{ progressValue }}%</strong></div>
          <div class="h-2.5 overflow-hidden rounded-full bg-cx-well"><div class="h-full rounded-full bg-cx-brand transition-all duration-500" :style="{ width: `${progressValue}%` }"></div></div>
        </div>
      </div>

      <div class="grid divide-y divide-cx-border-soft sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        <div class="p-4 sm:px-6">
          <p class="text-[10px] font-semibold uppercase tracking-wide text-cx-ink-3">Last deployment attempt</p>
          <p class="mt-1.5 text-sm font-semibold text-cx-ink">{{ provisioning?.last_attempt || 'No attempt recorded' }}</p>
        </div>
        <div class="p-4 sm:px-6">
          <p class="text-[10px] font-semibold uppercase tracking-wide text-cx-ink-3">Status provided by</p>
          <p class="mt-1.5 text-sm font-semibold text-cx-ink">{{ statusSource }}</p>
        </div>
        <div class="p-4 sm:px-6">
          <p class="text-[10px] font-semibold uppercase tracking-wide text-cx-ink-3">Facility ID used for tracking</p>
          <p class="mt-1.5 break-all font-mono text-sm font-semibold text-cx-ink">{{ facility.hfr_facility_id || 'Not linked' }}</p>
        </div>
      </div>

      <div class="border-t border-cx-border-soft px-4 py-4 sm:px-6">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 class="text-sm font-semibold text-cx-ink">Provisioned HMIS details</h3>
            <p class="mt-1 max-w-2xl text-xs leading-relaxed text-cx-ink-3">The published status API does not include service-unit configuration or a live site health check. These details will appear when the setup service exposes them.</p>
          </div>
          <span class="rounded-full border border-cx-border bg-cx-well px-2.5 py-1 text-[10px] font-medium text-cx-ink-3">Not reported by API</span>
        </div>
      </div>

      <div class="border-t border-cx-border-soft bg-cx-well/50 px-4 py-3 text-[11px] leading-relaxed text-cx-ink-3 sm:px-6">
        Facility identifiers: <span class="font-medium text-cx-ink-2">MFL {{ facility.mfl_code || '—' }}</span><span v-if="facility.registration_number"> · Registration {{ facility.registration_number }}</span><span v-if="facility.network"> · {{ facility.network }}</span>
      </div>
    </section>

    <div class="grid gap-5 xl:grid-cols-2">
      <section class="rounded-cx border border-cx-border bg-cx-surface p-5 shadow-cx">
        <div class="mb-4 flex items-center justify-between"><h2 class="text-base font-bold text-cx-ink">Invoices</h2><span class="rounded-full bg-cx-well px-2.5 py-1 text-[11px] font-semibold text-cx-ink-2">{{ invoices.length }}</span></div>
        <div v-if="!invoices.length" class="rounded-cx-sm bg-cx-well p-4 text-xs text-cx-ink-3">No outstanding invoices are linked to this facility.</div>
        <div v-else class="divide-y divide-cx-border-soft">
          <div v-for="invoice in invoices" :key="invoice.name" class="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0">
            <div>
              <p class="text-xs font-semibold text-cx-ink">{{ invoice.invoice_number || invoice.name }}</p>
              <p class="mt-1 text-[11px] text-cx-ink-3">Due {{ invoice.due_date || 'on receipt' }} · {{ pendingPaymentForInvoice(invoice) ? 'Payment verification pending' : invoiceStatus(invoice) }}</p>
              <p v-if="pendingPaymentForInvoice(invoice)" class="mt-1 text-[11px] font-semibold text-cx-warning-ink">
                M-Pesa report {{ pendingPaymentForInvoice(invoice).reference_no || pendingPaymentForInvoice(invoice).name }} is awaiting verification. Please wait before paying again.
              </p>
            </div>
            <div class="flex items-center gap-3">
              <strong class="text-sm text-cx-ink">{{ money(invoice.amount, invoice.currency) }}</strong>
              <button v-if="Number(invoice.amount) > 0 && !pendingPaymentForInvoice(invoice)" type="button" class="rounded-cx-sm bg-cx-success px-3 py-1.5 text-[11px] font-semibold text-cx-contrast" @click="emit('pay', invoice)">Choose payment</button>
              <span v-else-if="pendingPaymentForInvoice(invoice)" class="text-[11px] font-semibold text-cx-warning-ink">Verification pending</span>
            </div>
          </div>
        </div>
      </section>
      <section class="rounded-cx border border-cx-border bg-cx-surface p-5 shadow-cx">
        <div class="mb-4 flex items-center justify-between"><h2 class="text-base font-bold text-cx-ink">Payment history</h2><span class="rounded-full bg-cx-well px-2.5 py-1 text-[11px] font-semibold text-cx-ink-2">{{ payments.length }}</span></div>
        <div v-if="!payments.length" class="rounded-cx-sm bg-cx-well p-4 text-xs text-cx-ink-3">No payments have been matched to this facility’s invoices.</div>
        <div v-else class="divide-y divide-cx-border-soft">
          <div v-for="payment in payments" :key="`${payment.name}-${payment.invoice || ''}`" class="flex items-center justify-between gap-3 py-3 first:pt-0">
            <div>
              <p class="text-xs font-semibold text-cx-ink">{{ payment.mode_of_payment }} · {{ payment.reference_no || payment.name }}</p>
              <p class="mt-1 text-[11px] text-cx-ink-3">{{ payment.posting_date }}<span v-if="payment.invoice"> · Invoice {{ payment.invoice }}</span></p>
              <span class="mt-1 inline-flex rounded-full border px-2 py-0.5 text-[10px] font-semibold" :class="payment.status === 'Pending Verification' ? 'border-cx-warning-border bg-cx-warning-soft text-cx-warning-ink' : 'border-cx-success-border bg-cx-success-soft text-cx-success-ink'">{{ payment.status || 'Recorded' }}</span>
            </div>
            <strong class="shrink-0 text-sm text-cx-ink">{{ money(payment.amount) }}</strong>
          </div>
        </div>
      </section>
      <section class="rounded-cx border border-cx-border bg-cx-surface p-5 shadow-cx xl:col-span-2">
        <div class="mb-4 flex items-center justify-between"><h2 class="text-base font-bold text-cx-ink">Token orders</h2><span class="rounded-full bg-cx-well px-2.5 py-1 text-[11px] font-semibold text-cx-ink-2">{{ orders.length }}</span></div>
        <div v-if="!orders.length" class="rounded-cx-sm bg-cx-well p-4 text-xs text-cx-ink-3">No open orders are linked to this facility.</div>
        <div v-else class="grid gap-3 sm:grid-cols-2">
          <article v-for="order in orders" :key="order.name" class="rounded-cx-sm border border-cx-border-soft p-3"><p class="text-xs font-semibold text-cx-ink">{{ order.name }}</p><p class="mt-1 text-[11px] text-cx-ink-3">{{ order.transaction_date }} · {{ order.status }}</p><p class="mt-2 text-sm font-bold text-cx-ink">{{ money(order.grand_total, order.currency) }}</p></article>
        </div>
      </section>
    </div>
  </section>
</template>

