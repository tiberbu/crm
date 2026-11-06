<script setup>
import { computed, ref } from 'vue'
import CxIcon from './CxIcon.vue'
import { tokenBalanceText } from '@/utils/tokenBalance'
import { canTopUp, commercialOf, formatDate, money as formatMoney } from '@/utils/portalCommercial'

const props = defineProps({
  facility: { type: Object, required: true },
  defaultCurrency: { type: String, default: 'KES' },
})
const emit = defineEmits(['open-top-up', 'open-support'])

const commercial = computed(() => commercialOf(props.facility))
const plan = computed(() => commercial.value.plan)
const money = (amount, currency) => formatMoney(amount, currency || props.defaultCurrency, props.defaultCurrency)
const multipleFacilities = computed(() => (plan.value.facilities_on_plan ?? 1) > 1)
const sharedNote = computed(() => `For all ${plan.value.facilities_on_plan} facilities on this plan`)
const nextInvoice = computed(() => plan.value.next_invoice || null)
const nextInvoiceText = computed(() => {
  const next = nextInvoice.value
  if (!next?.date) return ''
  return `${next.projected ? 'Projected ' : ''}${formatDate(next.date)}`
})
const upcomingOpen = ref(false)
const scheduleRows = computed(() => (plan.value.schedule || []).slice(0, 8))
const hasFacilityAmounts = computed(
  () =>
    plan.value.facility_monthly_excl_vat != null || plan.value.facility_annual_excl_vat != null,
)
</script>

<template>
  <section class="rounded-cx border border-cx-border bg-cx-surface p-5 shadow-cx" data-testid="plan-panel">
    <p class="text-xs font-semibold text-cx-ink-3">Your plan</p>

    <div v-if="commercial.unavailable" class="mt-3 rounded-cx-sm bg-cx-well p-4 text-xs text-cx-ink-2" role="alert">
      We could not load your plan details. Try again shortly.
    </div>

    <div v-else-if="commercial.plan_type === 'time_bound'" class="mt-3">
      <div class="flex flex-wrap items-center gap-3">
        <h2 class="break-words text-lg font-semibold text-cx-ink" data-testid="plan-name">
          {{ plan.name || 'Plan' }}
        </h2>
        <span
          v-if="commercial.journey_label"
          class="rounded-full border border-cx-border-soft bg-cx-well px-2.5 py-1 text-[11px] font-semibold text-cx-ink-2"
          data-testid="plan-journey"
        >
          {{ commercial.journey_label }}
        </span>
        <span
          v-if="plan.status"
          class="rounded-full border border-cx-success-border bg-cx-success-soft px-2.5 py-1 text-[11px] font-semibold text-cx-success-ink"
          data-testid="plan-status"
        >
          {{ plan.status }}
        </span>
      </div>
      <dl class="mt-4 grid gap-x-8 gap-y-4 sm:grid-cols-2 xl:grid-cols-3">
        <div v-if="plan.cycle_label">
          <dt class="text-xs font-semibold text-cx-ink-3">Cycle</dt>
          <dd class="mt-1 text-sm font-semibold text-cx-ink" data-testid="plan-cycle">{{ plan.cycle_label }}</dd>
        </div>
        <div v-if="plan.term_label">
          <dt class="text-xs font-semibold text-cx-ink-3">Term</dt>
          <dd class="mt-1 text-sm font-semibold text-cx-ink" data-testid="plan-term">{{ plan.term_label }}</dd>
        </div>
        <div v-if="hasFacilityAmounts">
          <dt class="text-xs font-semibold text-cx-ink-3">Your facility’s amounts (excl. VAT)</dt>
          <dd class="mt-1 text-sm font-semibold text-cx-ink" data-testid="plan-facility-amount">
            <span v-if="plan.facility_monthly_excl_vat != null">Monthly {{ money(plan.facility_monthly_excl_vat, plan.currency) }}</span>
            <span v-if="plan.facility_monthly_excl_vat != null && plan.facility_annual_excl_vat != null"> · </span>
            <span v-if="plan.facility_annual_excl_vat != null">Annual {{ money(plan.facility_annual_excl_vat, plan.currency) }}</span>
          </dd>
        </div>
        <div v-if="plan.current_period">
          <dt class="text-xs font-semibold text-cx-ink-3">Current period</dt>
          <dd class="mt-1 text-sm font-semibold text-cx-ink" data-testid="plan-current-period">{{ plan.current_period }}</dd>
        </div>
        <div v-if="nextInvoice">
          <dt class="text-xs font-semibold text-cx-ink-3">Next invoice</dt>
          <dd class="mt-1 text-sm font-semibold text-cx-ink" data-testid="plan-next-invoice">
            {{ nextInvoice.label }} · {{ nextInvoiceText }} · {{ money(nextInvoice.amount_incl_vat, nextInvoice.currency || plan.currency) }}
          </dd>
        </div>
      </dl>
      <p v-if="multipleFacilities && (nextInvoice || scheduleRows.length)" class="mt-2 text-xs text-cx-ink-2" data-testid="plan-shared-note">
        {{ sharedNote }}
      </p>
      <div v-if="scheduleRows.length" class="mt-4">
        <button
          type="button"
          class="inline-flex min-h-10 items-center gap-1.5 rounded-cx-sm border border-cx-border bg-cx-surface px-3 py-2 text-xs font-semibold text-cx-brand hover:bg-cx-well"
          :aria-expanded="upcomingOpen"
          @click="upcomingOpen = !upcomingOpen"
        >
          <CxIcon name="chevron-down" class="size-3.5" :class="upcomingOpen ? 'rotate-180' : ''" />
          Upcoming invoices
        </button>
        <div v-if="upcomingOpen" class="mt-2 divide-y divide-cx-border-soft" data-testid="plan-schedule">
          <div v-for="row in scheduleRows" :key="row.label" class="flex flex-wrap items-center justify-between gap-3 py-2 text-xs">
            <span class="font-semibold text-cx-ink">
              {{ row.label }}
              <span v-if="row.state === 'invoiced'" class="font-normal text-cx-ink-2"> · Invoiced</span>
              <span v-else-if="row.state === 'failed'" class="font-normal text-cx-ink-2"> · Preparing</span>
            </span>
            <span class="text-cx-ink-2">{{ row.projected ? 'Projected ' : '' }}{{ formatDate(row.invoice_date) }}</span>
            <strong class="shrink-0 text-cx-ink">{{ money(row.amount_incl_vat, plan.currency) }}</strong>
          </div>
        </div>
      </div>
    </div>

    <div v-else-if="commercial.plan_type === 'token'" class="mt-3">
      <div class="flex flex-wrap items-center gap-3">
        <h2 class="break-words text-lg font-semibold text-cx-ink" data-testid="plan-name">
          {{ plan.name || facility.token_package || 'Token plan' }}
        </h2>
        <span
          v-if="commercial.journey_label"
          class="rounded-full border border-cx-border-soft bg-cx-well px-2.5 py-1 text-[11px] font-semibold text-cx-ink-2"
          data-testid="plan-journey"
        >
          {{ commercial.journey_label }}
        </span>
      </div>
      <p v-if="facility.token_quantity" class="mt-2 text-sm text-cx-ink-2">
        {{ Number(facility.token_quantity).toLocaleString() }} Care Tokens per package
      </p>
    </div>

    <div v-else class="mt-3">
      <h2 class="text-lg font-semibold text-cx-ink" data-testid="plan-name">No plan yet</h2>
      <p class="mt-1 text-sm text-cx-ink-2">Choose how this facility is billed.</p>
      <button
        v-if="canTopUp(facility)"
        type="button"
        class="mt-3 rounded-cx-sm bg-cx-brand px-4 py-2.5 text-xs font-semibold text-cx-contrast shadow-cx hover:bg-cx-brand-strong"
        @click="emit('open-top-up', facility, 'paid')"
      >
        Choose a plan
      </button>
      <button
        v-else
        type="button"
        class="mt-3 rounded-cx-sm border border-cx-border bg-cx-surface px-4 py-2.5 text-xs font-semibold text-cx-ink-2 hover:bg-cx-well"
        @click="emit('open-support', facility)"
      >
        Contact Network Support
      </button>
    </div>

    <div
      v-if="commercial.plan_type === 'time_bound' && commercial.has_tokens"
      class="mt-4 rounded-cx-sm border border-cx-border-soft bg-cx-well p-4"
      data-testid="plan-care-tokens"
    >
      <p class="text-xs font-semibold text-cx-ink-3">Care Tokens</p>
      <p class="mt-1 text-2xl font-semibold tracking-tight text-cx-brand">{{ tokenBalanceText(facility) }}</p>
    </div>
  </section>
</template>
