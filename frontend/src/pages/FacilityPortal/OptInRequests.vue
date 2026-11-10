<script setup>
// Opt-In and Self-Onboarding requests. A Network Opt-In request carries its live
// billing ledger (OptInLedger): summary, how payments work, quarterly schedule, quotes.
import { computed } from 'vue'
import CxIcon from './components/CxIcon.vue'
import OptInLedger from './components/OptInLedger.vue'

const props = defineProps({
  requests: { type: Array, required: true },
  // Bumped by the portal after a payment so every ledger reloads.
  refreshKey: { type: [Number, String], default: 0 },
})
const emit = defineEmits(['pay', 'issued'])

const isSelf = (request) => request.source === 'token_self_onboarding'
const hasSelfOnboarding = computed(() => props.requests.some(isSelf))
const hasNetworkOptIn = computed(() => props.requests.some((request) => !isSelf(request)))
const pageTitle = computed(() => {
  if (hasSelfOnboarding.value && hasNetworkOptIn.value) return 'Requests & quotations'
  return hasSelfOnboarding.value ? 'Self-Onboarding requests' : 'Opt-In Requests'
})
const pageDescription = computed(() => {
  if (hasSelfOnboarding.value && hasNetworkOptIn.value) {
    return 'Follow your Self-Onboarding requests and invited Network Opt-In submissions, quotations, and payments.'
  }
  return hasSelfOnboarding.value
    ? 'Your Self-Onboarding requests, quotations, and next steps in one place.'
    : 'Your Network Opt-In contract, payment schedule, invoices and quotations in one place. Each quarter is invoiced on its date; pay it from here.'
})

function statusClasses(status) {
  return String(status || '').toLowerCase() === 'processed'
    ? 'border-cx-success-border bg-cx-success-soft text-cx-success-ink'
    : 'border-cx-border bg-cx-well text-cx-ink-2'
}
</script>

<template>
  <div>
    <div>
      <h1 class="text-4xl font-semibold text-cx-ink tracking-tight leading-tight">{{ pageTitle }}</h1>
      <p class="mt-0.5 text-xs text-cx-ink-2">{{ pageDescription }}</p>
    </div>

    <div v-if="!requests.length" class="mt-6 rounded-cx border border-cx-border bg-cx-surface p-10 text-center text-xs text-cx-ink-2">
      <span class="mb-2 block text-3xl"><CxIcon name="clipboard-list" class="inline-block size-4 align-[-0.15em]" /></span>
      <p class="text-sm font-semibold text-cx-ink">No requests yet</p>
      <p class="mt-1">Your Self-Onboarding requests and invited Network Opt-In submissions will appear here.</p>
    </div>

    <div v-else class="mt-6 space-y-6">
      <article
        v-for="req in requests"
        :key="req.name"
        class="space-y-4 rounded-cx border border-cx-border bg-cx-surface p-4 shadow-cx sm:p-5"
        :data-testid="`optin-request-${req.name}`"
      >
        <header class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <h2 class="break-words text-base font-semibold text-cx-ink" data-testid="optin-request-network">{{ req.network || (isSelf(req) ? 'Self-Onboarding' : 'Network Opt-In') }}</h2>
              <span class="rounded-full border border-cx-border bg-cx-well px-2 py-0.5 text-[11px] font-semibold text-cx-ink-2">
                {{ isSelf(req) ? 'Self-Onboarding' : 'Network Opt-In' }}
              </span>
              <span class="rounded-full border px-2.5 py-0.5 text-[11px] font-semibold" :class="statusClasses(req.status)">
                {{ req.status }}
              </span>
            </div>
            <p class="mt-1 break-words text-xs text-cx-ink-2">
              <span class="font-mono">{{ req.name }}</span>
              <template v-if="!isSelf(req) && req.contract"> · Contract <span class="font-mono">{{ req.contract }}</span></template>
              <template v-if="!isSelf(req) && req.signatory"> · Signatory: {{ req.signatory }}</template>
            </p>
          </div>
          <span class="shrink-0 self-start rounded-cx-sm border border-cx-border bg-cx-well px-2.5 py-1 text-xs font-semibold text-cx-ink-2" data-testid="optin-request-facility-count">
            {{ req.facilities.length }} {{ req.facilities.length === 1 ? 'facility' : 'facilities' }}
          </span>
        </header>

        <OptInLedger
          v-if="!isSelf(req) && req.status === 'Processed'"
          :ois-number="req.name"
          :refresh-key="refreshKey"
          @pay="emit('pay', $event)"
          @issued="emit('issued', $event)"
        />

        <div v-else class="grid gap-3 text-xs sm:grid-cols-3">
          <div class="rounded-cx-sm border border-cx-border-soft bg-cx-well p-3">
            <span class="block text-xs font-medium text-cx-ink-3">Plan</span>
            <strong class="mt-1 block text-sm font-semibold text-cx-ink">{{ req.package?.display_name || req.plan_name || 'Not selected' }}</strong>
            <span v-if="req.package?.token_quantity" class="mt-0.5 block text-xs text-cx-ink-2">{{ req.package.token_quantity }} tokens</span>
          </div>
          <div class="rounded-cx-sm border border-cx-border-soft bg-cx-well p-3">
            <span class="block text-xs font-medium text-cx-ink-3">Open orders and invoices</span>
            <strong class="mt-1 block text-sm font-semibold text-cx-ink">{{ req.open_orders }} open · {{ req.open_invoices }} due</strong>
          </div>
          <div class="rounded-cx-sm border border-cx-border-soft bg-cx-well p-3">
            <span class="block text-xs font-medium text-cx-ink-3">Quotations</span>
            <span v-if="!req.quotes.length" class="mt-1 block text-sm font-semibold text-cx-ink-2">None yet</span>
            <ul v-else class="mt-1 space-y-0.5">
              <li v-for="quote in req.quotes" :key="quote" class="break-all font-mono text-xs font-semibold text-cx-ink">{{ quote }}</li>
            </ul>
          </div>
        </div>

        <div v-if="req.facilities.length">
          <h3 class="text-xs font-medium text-cx-ink-3">Facilities on this request</h3>
          <div class="mt-2 grid gap-2 sm:grid-cols-2">
            <div
              v-for="fac in req.facilities"
              :key="fac.mfl_code"
              class="flex min-w-0 flex-wrap items-center justify-between gap-x-2 gap-y-1 rounded-cx-sm border border-cx-border-soft bg-cx-well px-3 py-2 text-xs"
            >
              <span class="min-w-0 break-words font-semibold text-cx-ink"><CxIcon name="hospital" class="inline-block size-4 align-[-0.15em]" /> {{ fac.name }}</span>
              <span class="font-mono text-xs text-cx-ink-2">Facility ID {{ fac.facility_id || 'not linked yet' }} · MFL {{ fac.mfl_code }}</span>
            </div>
          </div>
        </div>
      </article>
    </div>
  </div>
</template>
