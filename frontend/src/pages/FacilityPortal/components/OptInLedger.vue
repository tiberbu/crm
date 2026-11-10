<script setup>
// The Opt-In billing ledger (spec P-124 to P-133): money at a glance, paying ahead,
// the quarterly schedule with its order → invoice → payment trail, and the yearly
// quotes. One component on the Opt-In Requests page and the facility page tab.
import { computed, onMounted, ref, watch } from 'vue'
import { call } from 'frappe-ui'
import CxIcon from './CxIcon.vue'
import { formatDate, money as formatMoney } from '@/utils/portalCommercial'
import {
  advanceLabels,
  advanceTotal,
  clampCount,
  payableInvoice,
  periodAction,
  periodRange,
  quotationPdfUrl,
  stateClasses,
  yearOpenByDefault,
  yearSummary,
} from '@/utils/optinLedger'

const props = defineProps({
  oisNumber: { type: String, required: true },
  // Bumped by the host after a payment so the ledger reloads.
  refreshKey: { type: [Number, String], default: 0 },
  // Facility page: the facility already has its own Quotes tab.
  showQuotes: { type: Boolean, default: true },
})
const emit = defineEmits(['pay', 'issued'])

const ledger = ref(null)
const loading = ref(false)
const error = ref('')
const updatedAt = ref('')
const count = ref(1)
const issuing = ref(false)
const issueError = ref('')
const issuedNotice = ref('')
const openYears = ref({})

const currency = computed(() => ledger.value?.currency || 'KES')
const money = (amount) => formatMoney(amount, currency.value)
const summary = computed(() => ledger.value?.summary || {})
const advance = computed(() => ledger.value?.advance || { allowed: false, next: [] })
const maxCount = computed(() => (advance.value.allowed ? advance.value.max_periods || 0 : 0))
const chosenTotal = computed(() => advanceTotal(advance.value.next, count.value))
const chosenRange = computed(() => periodRange(advanceLabels(advance.value.next, count.value)))
const years = computed(() => ledger.value?.years || [])
const otherInvoices = computed(() => ledger.value?.other_invoices || [])
const nextPayment = computed(() => summary.value.next_payment || null)

const tiles = computed(() => [
  { key: 'contract', label: 'Contract value', value: money(summary.value.contract_total), note: 'All years, incl. VAT' },
  { key: 'invoiced', label: 'Invoiced', value: money(summary.value.invoiced_total), note: 'Invoices issued so far' },
  { key: 'paid', label: 'Paid', value: money(summary.value.paid_total), note: summary.value.paid_ahead_total > 0 ? `${money(summary.value.paid_ahead_total)} paid ahead` : 'Payments received' },
  { key: 'outstanding', label: 'Outstanding', value: money(summary.value.outstanding_total), note: summary.value.overdue_total > 0 ? `${money(summary.value.overdue_total)} overdue` : 'On issued invoices' },
])

const nextPaymentText = computed(() => {
  const next = nextPayment.value
  if (!next) return 'Everything is paid'
  const when = formatDate(next.date)
  if (next.state === 'due' || next.state === 'overdue') return `${next.label} · due ${when}`
  return `${next.label} · invoice on ${when}`
})

async function load() {
  if (!props.oisNumber) return
  loading.value = true
  error.value = ''
  try {
    const result = await call('crm.api.optin_ledger.get_optin_ledger', { ois_number: props.oisNumber })
    setLedger(result?.message || result)
  } catch (err) {
    error.value = err?.messages?.[0] || 'We could not load your payment schedule.'
  } finally {
    loading.value = false
  }
}

function setLedger(data) {
  if (!data || typeof data !== 'object') return
  ledger.value = data
  updatedAt.value = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  count.value = clampCount(count.value, data.advance?.allowed ? data.advance.max_periods : 0) || 1
  const open = { ...openYears.value }
  ;(data.years || []).forEach((year, index) => {
    if (!(year.year in open)) open[year.year] = yearOpenByDefault(year, index)
  })
  openYears.value = open
}

function setCount(value) {
  count.value = clampCount(value, maxCount.value)
}

async function issue() {
  if (!advance.value.allowed || issuing.value) return
  issuing.value = true
  issueError.value = ''
  issuedNotice.value = ''
  try {
    const result = await call('crm.api.optin_ledger.issue_optin_periods', { ois_number: props.oisNumber, count: count.value })
    const data = result?.message || result || {}
    if (data.ledger) setLedger(data.ledger)
    const issued = data.issued || []
    issuedNotice.value = issued.length
      ? `${issued.length === 1 ? 'Invoice' : `${issued.length} invoices`} created: ${issued.map((row) => `${row.label} (${row.sales_invoice})`).join(', ')}. Choose Pay on each row below.`
      : ''
    if (data.error) issueError.value = `We stopped at one period: ${data.error}`
    emit('issued', issued)
  } catch (err) {
    issueError.value = err?.messages?.[0] || 'We could not create the invoices. Nothing was charged.'
  } finally {
    issuing.value = false
  }
}

function pay(source) {
  emit('pay', payableInvoice(source, props.oisNumber, currency.value))
}

function toggleYear(year) {
  openYears.value = { ...openYears.value, [year]: !openYears.value[year] }
}

function pdfUrl(quotation) {
  return quotationPdfUrl(quotation, { oisNumber: props.oisNumber })
}

onMounted(load)
watch(() => [props.oisNumber, props.refreshKey], load)
defineExpose({ reload: load })
</script>

<template>
  <section class="space-y-4" data-testid="optin-ledger" :aria-busy="loading">
    <div v-if="error && !ledger" class="flex flex-wrap items-center justify-between gap-2 rounded-cx-sm border border-cx-warning-border bg-cx-warning-soft/60 p-4 text-xs text-cx-warning-ink" role="alert">
      <span>{{ error }}</span>
      <button type="button" class="font-semibold underline" @click="load">Try again</button>
    </div>
    <div v-else-if="!ledger" class="rounded-cx-sm bg-cx-well p-4 text-xs text-cx-ink-2">Loading your payment schedule…</div>

    <template v-else>
      <!-- Money at a glance: sibling tiles share one label and value style. -->
      <div class="grid grid-cols-2 gap-2 lg:grid-cols-4" data-testid="ledger-summary">
        <div v-for="tile in tiles" :key="tile.key" class="min-w-0 rounded-cx-sm border border-cx-border-soft bg-cx-well p-3" :data-testid="`ledger-tile-${tile.key}`">
          <span class="block text-xs font-medium text-cx-ink-3">{{ tile.label }}</span>
          <strong class="mt-1 block break-words text-base font-semibold text-cx-ink">{{ tile.value }}</strong>
          <span class="mt-0.5 block text-xs text-cx-ink-2">{{ tile.note }}</span>
        </div>
      </div>

      <div class="flex flex-wrap items-center justify-between gap-3 rounded-cx-sm border border-cx-border bg-cx-surface p-3" data-testid="ledger-next-payment">
        <div class="flex min-w-0 items-center gap-2">
          <CxIcon name="clock" class="size-4 shrink-0 text-cx-brand" />
          <div class="min-w-0">
            <span class="block text-xs font-medium text-cx-ink-3">Next payment</span>
            <span class="block break-words text-sm font-semibold text-cx-ink">{{ nextPaymentText }}</span>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <strong v-if="nextPayment" class="text-sm font-semibold text-cx-ink">{{ money(nextPayment.amount) }}</strong>
          <button
            type="button"
            class="inline-flex min-h-9 items-center gap-1.5 rounded-cx-sm border border-cx-border px-2.5 text-xs font-semibold text-cx-ink-2 hover:bg-cx-well disabled:opacity-50"
            :disabled="loading"
            data-testid="ledger-refresh"
            @click="load"
          >
            <CxIcon name="refresh" class="size-3.5" :class="loading ? 'animate-spin' : ''" />
            <span>Updated {{ updatedAt }}</span>
          </button>
        </div>
      </div>

      <!-- Pay ahead: above the schedule so the call to action is on first view. -->
      <div class="rounded-cx border border-cx-border bg-cx-surface p-4 shadow-cx" data-testid="ledger-pay-ahead">
        <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div class="min-w-0 lg:max-w-md">
            <h3 class="text-sm font-semibold text-cx-ink">Pay ahead of your schedule</h3>
            <p class="mt-1 text-xs text-cx-ink-2">
              Invoices are issued automatically on the dates below. You can also pay early, one quarter or several, whenever you are ready.
            </p>
            <ol class="mt-3 space-y-1.5 text-xs text-cx-ink-2">
              <li class="flex gap-2"><span class="grid size-5 shrink-0 place-items-center rounded-full bg-cx-brand-soft text-[11px] font-semibold text-cx-brand-ink">1</span>Choose how many quarters to pay now.</li>
              <li class="flex gap-2"><span class="grid size-5 shrink-0 place-items-center rounded-full bg-cx-brand-soft text-[11px] font-semibold text-cx-brand-ink">2</span>Create the invoices. Each one keeps its contract due date, so nothing becomes due sooner.</li>
              <li class="flex gap-2"><span class="grid size-5 shrink-0 place-items-center rounded-full bg-cx-brand-soft text-[11px] font-semibold text-cx-brand-ink">3</span>Choose Pay on each invoice in the schedule: card, M-Pesa or bank transfer.</li>
            </ol>
          </div>

          <div v-if="advance.allowed" class="w-full rounded-cx-sm border border-cx-border-soft bg-cx-well p-3 lg:w-80" data-testid="ledger-advance-form">
            <span id="ledger-count-label" class="block text-xs font-medium text-cx-ink-3">Quarters to pay now</span>
            <div class="mt-2 flex items-center gap-2" role="group" aria-labelledby="ledger-count-label">
              <button type="button" class="grid size-9 place-items-center rounded-cx-sm border border-cx-border bg-cx-surface text-cx-ink-2 hover:bg-cx-well disabled:opacity-40" :disabled="count <= 1" aria-label="Fewer quarters" data-testid="ledger-count-minus" @click="setCount(count - 1)">
                <CxIcon name="minus" class="size-3.5" />
              </button>
              <span class="min-w-8 text-center text-base font-semibold text-cx-ink" aria-live="polite" data-testid="ledger-count">{{ count }}</span>
              <button type="button" class="grid size-9 place-items-center rounded-cx-sm border border-cx-border bg-cx-surface text-cx-ink-2 hover:bg-cx-well disabled:opacity-40" :disabled="count >= maxCount" aria-label="More quarters" data-testid="ledger-count-plus" @click="setCount(count + 1)">
                <CxIcon name="plus" class="size-3.5" />
              </button>
              <span class="text-xs text-cx-ink-2">of up to {{ maxCount }}</span>
            </div>
            <p class="mt-2 break-words text-xs text-cx-ink-2" data-testid="ledger-advance-range">{{ chosenRange }}</p>
            <button
              type="button"
              class="mt-3 inline-flex min-h-10 w-full items-center justify-center gap-1.5 rounded-cx-sm bg-cx-brand px-3 text-xs font-semibold text-cx-contrast shadow-cx hover:bg-cx-brand-strong disabled:opacity-60"
              :disabled="issuing"
              data-testid="ledger-issue"
              @click="issue"
            >
              <CxIcon name="receipt" class="size-3.5" />
              {{ issuing ? 'Creating…' : `Create ${count === 1 ? 'invoice' : `${count} invoices`} · ${money(chosenTotal)}` }}
            </button>
          </div>
          <div v-else class="w-full rounded-cx-sm border border-cx-border-soft bg-cx-well p-3 text-xs text-cx-ink-2 lg:w-80" data-testid="ledger-advance-blocked">
            <CxIcon name="info" class="mr-1 inline-block size-3.5 align-[-0.15em] text-cx-ink-3" />{{ advance.reason }}
          </div>
        </div>
        <p v-if="issuedNotice" class="mt-3 rounded-cx-sm border border-cx-success-border bg-cx-success-soft p-3 text-xs font-medium text-cx-success-ink" role="status" data-testid="ledger-issued">{{ issuedNotice }}</p>
        <p v-if="issueError" class="mt-3 rounded-cx-sm border border-cx-danger-border bg-cx-danger-soft p-3 text-xs font-medium text-cx-danger-ink" role="alert" data-testid="ledger-issue-error">{{ issueError }}</p>
      </div>

      <!-- The schedule, one block per contract year. -->
      <div class="rounded-cx border border-cx-border bg-cx-surface shadow-cx" data-testid="ledger-schedule">
        <div class="flex flex-wrap items-center justify-between gap-2 border-b border-cx-border-soft p-4">
          <h3 class="text-sm font-semibold text-cx-ink">Payment schedule</h3>
          <span class="text-xs text-cx-ink-2">{{ ledger.contract_status === 'Fully Executed' ? 'Quarterly, from your signed contract' : 'Projected until every signatory has signed' }}</span>
        </div>
        <div v-for="(year, index) in years" :key="year.year" class="border-b border-cx-border-soft last:border-b-0" :data-testid="`ledger-year-${year.year}`">
          <button
            type="button"
            class="flex w-full flex-wrap items-center justify-between gap-2 px-4 py-3 text-left hover:bg-cx-well"
            :aria-expanded="Boolean(openYears[year.year])"
            @click="toggleYear(year.year)"
          >
            <span class="flex items-center gap-2 text-sm font-semibold text-cx-ink">
              <CxIcon name="chevron-down" class="size-3.5 text-cx-ink-3 transition-transform" :class="openYears[year.year] ? '' : '-rotate-90'" />
              Year {{ year.year }}
            </span>
            <span class="text-xs text-cx-ink-2">{{ yearSummary(year).paid }} of {{ yearSummary(year).count }} paid · {{ money(yearSummary(year).total) }}</span>
          </button>
          <ul v-if="openYears[year.year]" class="divide-y divide-cx-border-soft px-4 pb-2">
            <li v-for="period in year.periods" :key="period.billing_key || period.label" class="grid gap-2 py-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center" :data-testid="`ledger-period-${period.billing_key}`">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="text-sm font-semibold text-cx-ink">{{ period.label }}</span>
                  <span class="rounded-full border px-2 py-0.5 text-[11px] font-semibold" :class="stateClasses(period.state)" :data-testid="`ledger-state-${period.billing_key}`">{{ period.state_label }}</span>
                  <span v-if="period.issued_early" class="text-xs text-cx-ink-2">Issued early</span>
                </div>
                <p class="mt-1 text-xs text-cx-ink-2">
                  <template v-if="period.sales_invoice">Invoiced {{ formatDate(period.invoice_date) }} · due {{ formatDate(period.due_date) }}</template>
                  <template v-else>Invoice on {{ formatDate(period.scheduled_date) }} · due {{ formatDate(period.due_date) }}</template>
                </p>
                <p v-if="period.sales_order || period.sales_invoice || period.payments.length" class="mt-1 flex flex-wrap items-center gap-1 break-all font-mono text-xs text-cx-ink-2" :data-testid="`ledger-trail-${period.billing_key}`">
                  <span v-if="period.sales_order">Order {{ period.sales_order }}</span>
                  <CxIcon v-if="period.sales_order && period.sales_invoice" name="arrow-right" class="size-3 text-cx-ink-3" />
                  <span v-if="period.sales_invoice">Invoice {{ period.sales_invoice }}</span>
                  <template v-for="payment in period.payments" :key="payment.name">
                    <CxIcon name="arrow-right" class="size-3 text-cx-ink-3" />
                    <span>{{ payment.status === 'Recorded' ? 'Paid' : 'Payment reported' }} {{ formatDate(payment.date) }}{{ payment.mode ? ` · ${payment.mode}` : '' }}</span>
                  </template>
                </p>
              </div>
              <div class="flex items-center justify-between gap-3 sm:justify-end">
                <strong class="text-sm font-semibold text-cx-ink">{{ money(period.sales_invoice && period.outstanding > 0 ? period.outstanding : period.amount) }}</strong>
                <button
                  v-if="periodAction(period) === 'pay'"
                  type="button"
                  class="min-h-9 rounded-cx-sm bg-cx-brand px-3 text-xs font-semibold text-cx-contrast hover:bg-cx-brand-strong"
                  :data-testid="`ledger-pay-${period.billing_key}`"
                  @click="pay(period)"
                >
                  Pay
                </button>
                <span v-else-if="periodAction(period) === 'pending'" class="text-xs font-semibold text-cx-warning-ink">Verifying payment</span>
              </div>
            </li>
          </ul>
        </div>
      </div>

      <div v-if="otherInvoices.length" class="rounded-cx border border-cx-border bg-cx-surface p-4 shadow-cx" data-testid="ledger-other-invoices">
        <h3 class="text-sm font-semibold text-cx-ink">Other invoices on this request</h3>
        <ul class="mt-2 divide-y divide-cx-border-soft">
          <li v-for="invoice in otherInvoices" :key="invoice.name" class="flex flex-wrap items-center justify-between gap-3 py-3">
            <div class="min-w-0">
              <p class="break-all font-mono text-xs font-semibold text-cx-ink">{{ invoice.name }}</p>
              <p class="mt-1 text-xs text-cx-ink-2">Invoiced {{ formatDate(invoice.invoice_date) }} · due {{ formatDate(invoice.due_date) }}</p>
            </div>
            <div class="flex items-center gap-3">
              <span class="rounded-full border px-2 py-0.5 text-[11px] font-semibold" :class="stateClasses(invoice.outstanding > 0 ? 'due' : 'paid')">{{ invoice.outstanding > 0 ? 'Due' : 'Paid' }}</span>
              <strong class="text-sm font-semibold text-cx-ink">{{ money(invoice.outstanding > 0 ? invoice.outstanding : invoice.amount) }}</strong>
              <button v-if="invoice.outstanding > 0" type="button" class="min-h-9 rounded-cx-sm bg-cx-brand px-3 text-xs font-semibold text-cx-contrast hover:bg-cx-brand-strong" @click="pay({ ...invoice, sales_invoice: invoice.name, invoice_total: invoice.amount })">Pay</button>
            </div>
          </li>
        </ul>
      </div>

      <div v-if="showQuotes && ledger.quotes.length" class="rounded-cx border border-cx-border bg-cx-surface p-4 shadow-cx" data-testid="ledger-quotes">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h3 class="text-sm font-semibold text-cx-ink">Yearly quotations</h3>
          <span class="text-xs text-cx-ink-2">One per contract year. Open one to see its lines.</span>
        </div>
        <ul class="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          <li v-for="quote in ledger.quotes" :key="quote.name">
            <a
              :href="pdfUrl(quote.name)"
              target="_blank"
              rel="noopener"
              class="flex items-center justify-between gap-3 rounded-cx-sm border border-cx-border-soft bg-cx-well px-3 py-2.5 hover:border-cx-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cx-brand/40"
              :data-testid="`ledger-quote-${quote.name}`"
            >
              <span class="min-w-0">
                <span class="block text-sm font-semibold text-cx-ink">Year {{ quote.year }}</span>
                <span class="block break-all font-mono text-xs text-cx-ink-2">{{ quote.name }}</span>
                <span class="block text-xs text-cx-ink-2">{{ quote.status_label }}</span>
              </span>
              <span class="flex shrink-0 items-center gap-1.5 text-sm font-semibold text-cx-ink">
                {{ money(quote.amount) }}
                <CxIcon name="file-text" class="size-4 text-cx-brand" />
              </span>
            </a>
          </li>
        </ul>
      </div>
    </template>
  </section>
</template>
