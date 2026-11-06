<script setup>
import { computed, nextTick, ref } from 'vue'
import CxIcon from './CxIcon.vue'
import JourneyStage from './JourneyStage.vue'
import { invoiceStatus } from '@/utils/portalOrderState'
import {
  commercialOf,
  formatDate,
  money,
  orderStatus,
  orderTitle,
  rowFacilityMfls,
  sortInvoices,
  stageStates,
} from '@/utils/portalCommercial'

const props = defineProps({
  facility: { type: Object, required: true },
  orders: { type: Array, default: () => [] },
  invoices: { type: Array, default: () => [] },
  payments: { type: Array, default: () => [] },
  busyOrder: { type: String, default: '' },
  accountLevelCount: { type: Number, default: 0 },
  defaultCurrency: { type: String, default: 'KES' },
  tokenPackages: { type: Array, default: () => [] },
})
const emit = defineEmits(['review-order', 'create-invoice', 'pay', 'open-billing'])

const commercial = computed(() => commercialOf(props.facility))
const showQuote = computed(
  () => commercial.value.journey === 'network_optin' || commercial.value.quotes.length > 0,
)
const sortedInvoices = computed(() => sortInvoices(props.invoices))
const stages = computed(() =>
  stageStates({
    showQuote: showQuote.value,
    quotes: commercial.value.quotes,
    orders: props.orders,
    invoices: props.invoices,
    payments: props.payments,
  }),
)
const invoicedOrderNames = computed(() => {
  const names = new Set()
  for (const invoice of props.invoices) {
    for (const name of invoice.sales_orders || []) names.add(String(name))
  }
  return names
})

const quoteStage = ref(null)
const orderStage = ref(null)
const invoiceStage = ref(null)
const paymentStage = ref(null)

const stageRefs = { quote: quoteStage, order: orderStage, invoice: invoiceStage, payment: paymentStage }

function stageRows(key) {
  if (key === 'quote') return commercial.value.quotes
  if (key === 'order') return props.orders
  if (key === 'invoice') return sortedInvoices.value
  return props.payments
}

function pendingPaymentForInvoice(invoice) {
  if (!invoice?.name) return null
  return (
    (props.payments || []).find((payment) => {
      if (payment.status !== 'Pending Verification') return false
      const names = payment.invoice_names?.length
        ? payment.invoice_names
        : payment.invoice
          ? [payment.invoice]
          : []
      return names.some((name) => String(name) === String(invoice.name))
    }) || null
  )
}

function hasQuote(quoteName) {
  if (!quoteName) return false
  return commercial.value.quotes.some((quote) => String(quote.name) === String(quoteName))
}

function hasOrder(orderName) {
  if (!orderName) return false
  return props.orders.some((order) => String(order.name) === String(orderName))
}

function jumpTo(name, stageKey) {
  const stageRef = stageRefs[stageKey]
  if (stageRef?.value?.expand) stageRef.value.expand()
  nextTick(() => {
    const target = document.getElementById(`doc-${name}`)
    if (!target) return
    target.scrollIntoView({ behavior: 'smooth', block: 'center' })
    target.focus({ preventScroll: true })
  })
}

function moneyFor(row) {
  return money(row.amount ?? row.grand_total ?? 0, row.currency || props.defaultCurrency, props.defaultCurrency)
}

function invoiceStatusLabel(invoice) {
  if (Number(invoice.amount) > 0) return invoiceStatus(invoice).label
  return 'Paid'
}

function scheduleNote(order) {
  if (!order.schedule_governed || invoicedOrderNames.value.has(order.name)) return ''
  const next = commercial.value.plan?.next_invoice
  return next?.date
    ? `We will issue this invoice on your billing schedule (Projected ${formatDate(next.date)}).`
    : 'We will issue this invoice on your billing schedule.'
}

function invoiceEmptyText() {
  const next = commercial.value.plan?.next_invoice
  if (commercial.value.plan_type === 'time_bound' && next?.date) {
    return `No invoices yet. Your first invoice is due to be issued on ${formatDate(next.date)}.`
  }
  return 'No invoices yet. An invoice is issued after your order is confirmed.'
}

const emptyTexts = {
  quote: 'Your quote will appear here once it is ready.',
  order: 'No orders yet. Your order appears here once it is created.',
  payment: 'No payments yet. Payments appear here after you pay an invoice.',
}

function mflCount(row) {
  return rowFacilityMfls(row).length
}
</script>

<template>
  <div class="space-y-5" data-testid="billing-journey">
    <ol aria-label="Billing progress" class="grid gap-2 sm:grid-cols-4" data-testid="journey-stepper">
      <li
        v-for="stage in stages"
        :key="stage.key"
        class="flex items-center gap-2 sm:flex-col sm:items-start sm:gap-1.5"
        :data-state="stage.state"
        :aria-current="stage.state === 'current' ? 'step' : undefined"
      >
        <span
          class="grid size-6 shrink-0 place-items-center rounded-full border text-[11px] font-semibold"
          :class="{
            'border-cx-success-border bg-cx-success-soft text-cx-success-ink': stage.state === 'done',
            'border-cx-brand bg-cx-brand-soft text-cx-brand-ink': stage.state === 'current',
            'border-cx-border bg-cx-well text-cx-ink-3': stage.state === 'upcoming',
          }"
        >
          <CxIcon v-if="stage.state === 'done'" name="check" class="size-3.5" />
          <span v-else-if="stage.state === 'current'" class="size-2 animate-pulse rounded-full bg-cx-brand"></span>
          <span v-else class="size-1.5 rounded-full bg-cx-ink-3/40"></span>
        </span>
        <span class="text-xs leading-snug" :class="stage.state === 'upcoming' ? 'text-cx-ink-3' : 'font-semibold text-cx-ink'">{{ stage.title }}</span>
      </li>
    </ol>

    <JourneyStage
      v-if="stages.some((stage) => stage.key === 'quote')"
      ref="quoteStage"
      stage-key="quote"
      title="Quotes"
      :rows="stageRows('quote')"
      :empty-text="emptyTexts.quote"
    >
      <template #default="{ row }">
        <div
          id="doc-{{ row.name }}"
          class="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 outline-none"
          tabindex="-1"
        >
          <div class="min-w-0">
            <p class="break-all font-mono text-xs font-semibold text-cx-ink">{{ row.name }}</p>
            <p class="mt-1 text-xs text-cx-ink-2">{{ row.label }}</p>
          </div>
          <div class="flex items-center gap-3">
            <span
              class="shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-semibold"
              :class="
                row.status_label === 'Accepted'
                  ? 'border-cx-success-border bg-cx-success-soft text-cx-success-ink'
                  : 'border-cx-border bg-cx-well text-cx-ink-2'
              "
            >
              {{ row.status_label }}
            </span>
            <strong class="shrink-0 text-sm text-cx-ink">{{ moneyFor(row) }}</strong>
          </div>
        </div>
      </template>
    </JourneyStage>

    <JourneyStage
      ref="orderStage"
      stage-key="order"
      title="Orders"
      :rows="stageRows('order')"
      :empty-text="emptyTexts.order"
    >
      <template #default="{ row }">
        <div
          id="doc-{{ row.name }}"
          class="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 outline-none"
          tabindex="-1"
          :data-testid="`facility-order-${row.name}`"
        >
          <div class="min-w-0">
            <p class="break-words text-sm font-semibold text-cx-ink">{{ orderTitle(row, tokenPackages) }}</p>
            <p class="mt-1 break-all font-mono text-xs text-cx-ink-2">Order {{ row.name }} · {{ row.transaction_date }}</p>
            <p v-if="row.quotation" class="mt-1 text-xs text-cx-ink-2">
              <button
                v-if="hasQuote(row.quotation)"
                type="button"
                class="font-semibold text-cx-brand underline-offset-2 hover:underline"
                @click="jumpTo(row.quotation, 'quote')"
              >
                From quote {{ row.quotation }}
              </button>
              <template v-else>From quote {{ row.quotation }}</template>
            </p>
            <p v-if="mflCount(row) > 1" class="mt-1 text-xs text-cx-ink-2">Covers {{ mflCount(row) }} facilities</p>
            <p v-if="scheduleNote(row)" class="mt-1 text-xs text-cx-ink-2">{{ scheduleNote(row) }}</p>
          </div>
          <div class="flex min-w-0 items-center justify-end gap-3">
            <span
              class="shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-semibold"
              :class="row.is_draft ? 'border-cx-warning-border bg-cx-warning-soft text-cx-warning-ink' : 'border-cx-border bg-cx-well text-cx-ink-2'"
              :data-testid="`facility-order-status-${row.name}`"
            >
              {{ orderStatus(row) }}
            </span>
            <strong class="shrink-0 text-sm text-cx-ink">{{ moneyFor(row) }}</strong>
            <button
              v-if="row.is_draft"
              type="button"
              class="rounded-cx-sm bg-cx-brand px-3 py-1.5 text-xs font-semibold text-cx-contrast hover:bg-cx-brand-strong"
              :data-testid="`facility-review-order-${row.name}`"
              @click="emit('review-order', row)"
            >
              Review order and pay
            </button>
            <button
              v-else-if="row.can_create_invoice"
              type="button"
              class="rounded-cx-sm bg-cx-ink px-3 py-1.5 text-xs font-semibold text-cx-contrast hover:bg-cx-ink-hover disabled:opacity-60"
              :disabled="busyOrder === row.name"
              :data-testid="`facility-create-invoice-${row.name}`"
              @click="emit('create-invoice', row)"
            >
              {{ busyOrder === row.name ? 'Generating…' : 'Generate invoice' }}
            </button>
          </div>
        </div>
      </template>
    </JourneyStage>

    <JourneyStage
      ref="invoiceStage"
      stage-key="invoice"
      title="Invoices"
      :rows="stageRows('invoice')"
      :empty-text="invoiceEmptyText()"
      section-id="facility-invoices"
    >
      <template #default="{ row }">
        <div
          id="doc-{{ row.name }}"
          class="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 outline-none"
          tabindex="-1"
        >
          <div class="min-w-0">
            <p class="break-all font-mono text-xs font-semibold text-cx-ink">{{ row.invoice_number || row.name }}</p>
            <p class="mt-1 text-xs text-cx-ink-2">Due {{ row.due_date || 'on receipt' }}</p>
            <p v-if="row.sales_orders?.length" class="mt-1 text-xs text-cx-ink-2">
              <template v-for="(orderName, index) in row.sales_orders" :key="orderName">
                <button
                  v-if="hasOrder(orderName)"
                  type="button"
                  class="font-semibold text-cx-brand underline-offset-2 hover:underline"
                  @click="jumpTo(orderName, 'order')"
                >
                  For order {{ orderName }}
                </button>
                <template v-else>For order {{ orderName }}</template>
                <template v-if="index < row.sales_orders.length - 1">, </template>
              </template>
            </p>
            <p v-if="mflCount(row) > 1" class="mt-1 text-xs text-cx-ink-2">Covers {{ mflCount(row) }} facilities</p>
            <p
              v-if="pendingPaymentForInvoice(row)"
              class="mt-1 text-xs font-semibold text-cx-warning-ink"
            >
              M-Pesa report {{ pendingPaymentForInvoice(row).reference_no || pendingPaymentForInvoice(row).name }} is awaiting verification. Please wait before paying again.
            </p>
          </div>
          <div class="flex items-center gap-3">
            <span
              class="shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-semibold"
              :class="
                pendingPaymentForInvoice(row)
                  ? 'border-cx-warning-border bg-cx-warning-soft text-cx-warning-ink'
                  : Number(row.amount) > 0
                    ? 'border-cx-border bg-cx-well text-cx-ink-2'
                    : 'border-cx-success-border bg-cx-success-soft text-cx-success-ink'
              "
            >
              {{ pendingPaymentForInvoice(row) ? 'Verification pending' : invoiceStatusLabel(row) }}
            </span>
            <strong class="shrink-0 text-sm text-cx-ink">{{ moneyFor(row) }}</strong>
            <button
              v-if="Number(row.amount) > 0 && !pendingPaymentForInvoice(row)"
              type="button"
              class="rounded-cx-sm bg-cx-success px-3 py-1.5 text-xs font-semibold text-cx-contrast"
              @click="emit('pay', row)"
            >
              Choose payment
            </button>
          </div>
        </div>
      </template>
    </JourneyStage>

    <JourneyStage
      ref="paymentStage"
      stage-key="payment"
      title="Payments"
      :rows="stageRows('payment')"
      :empty-text="emptyTexts.payment"
    >
      <template #default="{ row }">
        <div
          id="doc-{{ row.name }}"
          class="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 outline-none"
          tabindex="-1"
        >
          <div class="min-w-0">
            <p class="break-words text-xs font-semibold text-cx-ink">
              {{ row.mode_of_payment }} · {{ row.reference_no || row.name }}
            </p>
            <p class="mt-1 text-xs text-cx-ink-2">
              {{ row.posting_date }}
              <span v-if="row.invoice">
                ·
                <button
                  v-if="sortedInvoices.some((invoice) => String(invoice.name) === String(row.invoice))"
                  type="button"
                  class="font-semibold text-cx-brand underline-offset-2 hover:underline"
                  @click="jumpTo(row.invoice, 'invoice')"
                >
                  Pays invoice {{ row.invoice }}
                </button>
                <template v-else>Pays invoice {{ row.invoice }}</template>
              </span>
            </p>
            <span
              class="mt-1 inline-flex rounded-full border px-2 py-0.5 text-[11px] font-semibold"
              :class="
                row.status === 'Pending Verification'
                  ? 'border-cx-warning-border bg-cx-warning-soft text-cx-warning-ink'
                  : 'border-cx-success-border bg-cx-success-soft text-cx-success-ink'
              "
            >
              {{ row.status || 'Recorded' }}
            </span>
          </div>
          <strong class="shrink-0 text-sm text-cx-ink">{{ moneyFor(row) }}</strong>
        </div>
      </template>
    </JourneyStage>

    <div
      v-if="accountLevelCount > 0"
      class="flex flex-wrap items-center justify-between gap-2 rounded-cx-sm bg-cx-well p-3 text-xs text-cx-ink-2"
    >
      <span>{{ accountLevelCount }} account-level records are not tied to one facility.</span>
      <button type="button" class="font-semibold text-cx-brand underline-offset-2 hover:underline" @click="emit('open-billing')">
        View in Billing <CxIcon name="chevron-right" class="inline size-3" />
      </button>
    </div>
  </div>
</template>
