<script setup>
// One facility card for the Dashboard and Facilities views. The name has its own row so
// a long name or a long readiness label never draws over the other (docs/cx-portal-token-alerts-and-ui-review.md, UI-1/UI-2).
import { computed } from 'vue'
import CxIcon from './CxIcon.vue'
import { facilityId } from '@/utils/facilityId'
import { tokenBalance, tokenBalanceText } from '@/utils/tokenBalance'

const props = defineProps({
  facility: { type: Object, required: true },
  readinessLabel: { type: String, required: true },
  money: { type: Function, required: true },
  paymentPending: { type: Boolean, default: false },
  // The owner's low-token alert for this facility, if any.
  alert: { type: Object, default: null },
})
const emit = defineEmits(['open', 'top-up', 'pay'])

const fid = computed(() => facilityId(props.facility))
const balanceKnown = computed(() => tokenBalance(props.facility).known)
const outstanding = computed(
  () => props.facility.invoice_summary?.has_outstanding,
)
</script>

<template>
  <article
    class="flex min-w-0 cursor-pointer flex-col rounded-cx border border-cx-border bg-cx-surface p-5 shadow-cx transition hover:border-cx-brand"
    data-testid="facility-card"
    @click="emit('open', facility, $event)"
  >
    <button
      type="button"
      class="line-clamp-2 w-full break-words text-left text-base font-semibold leading-snug text-cx-ink underline-offset-2 hover:text-cx-brand-strong hover:underline"
      :title="facility.facility_name"
      @click.stop="emit('open', facility)"
    >
      {{ facility.facility_name }}
    </button>
    <!-- Level and Facility ID each get their own row on a shared label column so the
         values line up; the MFL code stays off the card (it lives in the drawer). -->
    <dl
      class="mt-3 grid grid-cols-[5.5rem_minmax(0,1fr)] gap-x-3 gap-y-1.5 border-t border-cx-border-soft pt-3 text-xs leading-snug"
      data-testid="facility-card-ids"
    >
      <dt class="text-cx-ink-3">Level</dt>
      <dd class="break-words font-medium text-cx-ink-2">
        {{ facility.keph_level || '—' }}
      </dd>
      <dt class="text-cx-ink-3">Facility ID</dt>
      <dd
        class="truncate"
        :class="
          fid
            ? 'font-mono font-semibold text-cx-ink'
            : 'font-medium italic text-cx-ink-3'
        "
        data-testid="facility-card-fid"
      >
        {{ fid || 'Not linked yet' }}
      </dd>
    </dl>
    <div class="mt-3 flex flex-wrap items-center gap-1.5">
      <span
        class="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-semibold"
        :class="
          facility.go_live
            ? 'border-cx-success-border bg-cx-success-soft text-cx-success-ink'
            : 'border-cx-warning-border bg-cx-warning-soft text-cx-warning-ink'
        "
        data-testid="facility-readiness"
      >
        <span
          class="size-1.5 rounded-full"
          :class="facility.go_live ? 'bg-cx-success' : 'bg-cx-warning'"
        ></span>
        {{ readinessLabel }}
      </span>
      <span
        v-if="facility.network"
        class="inline-flex min-w-0 max-w-full items-center gap-1 rounded-cx-sm border border-cx-border-soft bg-cx-well px-1.5 py-0.5 text-[11px] font-medium text-cx-ink-2"
        data-testid="facility-partner"
      >
        <CxIcon name="globe" class="size-3.5 shrink-0" />
        <span class="truncate">{{ facility.network }}</span>
      </span>
    </div>

    <dl
      class="mt-4 space-y-1.5 rounded-cx-sm border border-cx-border-soft bg-cx-well p-3 text-xs"
    >
      <div class="flex items-baseline justify-between gap-3">
        <dt class="shrink-0 text-cx-ink-3">Active plan</dt>
        <dd class="min-w-0 text-right font-semibold text-cx-ink">
          {{ facility.token_package || 'None' }}
        </dd>
      </div>
      <div
        v-if="facility.recent_purchase"
        class="flex items-baseline justify-between gap-3 text-xs"
      >
        <dt class="shrink-0 text-cx-ink-3">Recent order</dt>
        <dd class="min-w-0 text-right text-cx-ink">
          {{
            money(
              facility.recent_purchase.amount,
              facility.recent_purchase.currency,
            )
          }}
          ({{ facility.recent_purchase.date }})
        </dd>
      </div>
      <div class="flex items-baseline justify-between gap-3">
        <dt class="shrink-0 text-cx-ink-3">Available tokens</dt>
        <dd
          class="inline-flex min-w-0 items-center gap-1 text-right font-semibold"
          :class="balanceKnown ? 'text-cx-brand' : 'text-cx-ink-3'"
          :data-testid="`facility-tokens-${facility.mfl_code}`"
        >
          <CxIcon v-if="balanceKnown" name="coins" class="size-4 shrink-0" />{{
            tokenBalanceText(facility, ' tokens')
          }}
        </dd>
      </div>
      <div
        v-if="alert?.enabled"
        class="flex items-baseline justify-between gap-3 text-xs"
        :data-testid="`facility-alert-${facility.mfl_code}`"
      >
        <dt class="shrink-0 text-cx-ink-3">Low-token alert</dt>
        <dd class="inline-flex items-center gap-1 text-right text-cx-ink-2">
          <CxIcon name="bell" class="size-3.5 shrink-0" />at
          {{ Number(alert.threshold).toLocaleString() }} tokens
        </dd>
      </div>
      <div
        v-if="outstanding"
        class="flex items-baseline justify-between gap-3 border-t border-cx-border-soft pt-1.5"
      >
        <dt class="shrink-0 font-semibold text-cx-warning-ink">Amount due</dt>
        <dd class="text-right font-semibold text-cx-warning-ink">
          {{
            money(
              facility.invoice_summary.outstanding_amount,
              facility.invoice_summary.currency,
            )
          }}
        </dd>
      </div>
    </dl>

    <div class="mt-auto pt-4">
      <div class="space-y-2 border-t border-cx-border-soft pt-3">
        <button
          v-if="outstanding && !paymentPending"
          type="button"
          class="flex w-full items-center justify-center gap-1.5 rounded-cx-sm bg-cx-success px-3 py-2 text-xs font-semibold text-cx-contrast shadow-cx transition hover:bg-cx-success"
          @click.stop="emit('pay', facility)"
        >
          <CxIcon name="phone" class="size-4 shrink-0" />
          <span class="truncate"
            >Pay
            {{
              money(
                facility.invoice_summary.outstanding_amount,
                facility.invoice_summary.currency,
              )
            }}
            by M-Pesa</span
          >
        </button>
        <span
          v-else-if="outstanding"
          class="block text-center text-xs font-semibold text-cx-warning-ink"
        >
          Payment verification pending
        </span>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="flex-1 whitespace-nowrap rounded-cx-sm bg-cx-ink px-3 py-2 text-xs font-semibold text-cx-contrast transition hover:bg-cx-ink-hover"
            @click.stop="emit('top-up', facility)"
          >
            + Top up tokens
          </button>
          <button
            type="button"
            class="whitespace-nowrap rounded-cx-sm border border-cx-border bg-cx-surface px-2.5 py-2 text-xs font-semibold text-cx-ink-2 hover:bg-cx-well"
            :data-testid="`facility-details-${facility.mfl_code}`"
            @click.stop="emit('open', facility)"
          >
            Details →
          </button>
        </div>
      </div>
    </div>
  </article>
</template>
