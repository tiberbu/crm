<script setup>
import { computed } from 'vue'
import CxIcon from './components/CxIcon.vue'
const props = defineProps({
  requests: { type: Array, required: true },
})
const hasSelfOnboarding = computed(() =>
  props.requests.some((request) => request.source === 'token_self_onboarding'),
)
const hasNetworkOptIn = computed(() =>
  props.requests.some((request) => request.source !== 'token_self_onboarding'),
)
const pageTitle = computed(() => {
  if (hasSelfOnboarding.value && hasNetworkOptIn.value) return 'Requests & quotations'
  return hasSelfOnboarding.value ? 'Self-Onboarding requests' : 'Opt-In Requests'
})
const pageDescription = computed(() => {
  if (hasSelfOnboarding.value && hasNetworkOptIn.value) {
    return 'Follow your Self-Onboarding requests and invited Network Opt-In submissions, quotations, and progress.'
  }
  return hasSelfOnboarding.value
    ? 'Your Self-Onboarding requests, quotations, and next steps in one place.'
    : 'Your invited Network Opt-In submissions, quotations, and enrollment progress in one place.'
})
</script>

<template>
  <div>
    <div>
      <h1 class="text-4xl font-bold text-cx-ink tracking-tight leading-tight">{{ pageTitle }}</h1>
      <p class="text-xs text-cx-ink-3 mt-0.5">{{ pageDescription }}</p>
    </div>

    <div v-if="!requests.length" class="mt-6 rounded-cx border border-cx-border bg-cx-surface p-10 text-center text-xs text-cx-ink-3">
      <span class="mb-2 block text-3xl"><CxIcon name="clipboard-list" class="inline-block size-4 align-[-0.15em]" /></span>
      <p class="text-sm font-semibold text-cx-ink">No requests yet</p>
      <p class="mt-1">Your Self-Onboarding requests and invited Network Opt-In submissions will appear here.</p>
    </div>

    <div v-else class="space-y-4 mt-6">
      <article
        v-for="req in requests"
        :key="req.name"
        class="space-y-4 rounded-cx border border-cx-border bg-cx-surface p-5 shadow-cx"
      >
        <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <span class="font-semibold text-sm text-cx-ink">{{ req.network }}</span>
              <span class="rounded-full border border-cx-border bg-cx-well px-2 py-0.5 text-[10px] font-semibold text-cx-ink-2">
                {{ req.source === 'token_self_onboarding' ? 'Self-Onboarding' : 'Network Opt-In' }}
              </span>
              <span class="rounded-full border border-cx-border bg-cx-well px-2.5 py-0.5 text-[11px] font-semibold text-cx-ink-2">
                {{ req.status }}
              </span>
              <span v-if="req.source !== 'token_self_onboarding' && req.contract" class="font-mono text-[11px] text-cx-ink-3">Contract: {{ req.contract }}</span>
            </div>
            <p class="mt-1 text-[11px] text-cx-ink-3">
              {{ req.name }}
              <span v-if="req.source !== 'token_self_onboarding' && req.signatory"> · Signatory: {{ req.signatory }}</span>
            </p>
          </div>
          <span class="shrink-0 rounded-cx-sm border border-cx-border bg-cx-well px-2.5 py-1 text-[11px] font-semibold text-cx-ink-2">
            {{ req.facilities.length }} {{ req.facilities.length === 1 ? 'facility' : 'facilities' }}
          </span>
        </div>

        <div v-if="req.facilities.length" class="grid gap-2 sm:grid-cols-2">
          <div
            v-for="fac in req.facilities"
            :key="fac.mfl_code"
            class="flex items-center justify-between rounded-cx-sm border border-cx-border-soft bg-cx-well px-3 py-2 text-xs"
          >
            <span class="truncate font-semibold text-cx-ink"><CxIcon name="hospital" class="inline-block size-4 align-[-0.15em]" /> {{ fac.name }}</span>
            <span class="ml-2 shrink-0 font-mono text-[11px] text-cx-ink-3">Facility ID {{ fac.facility_id || 'not linked yet' }} · MFL {{ fac.mfl_code }}</span>
          </div>
        </div>

        <div class="grid gap-3 text-xs sm:grid-cols-3">
          <div class="rounded-cx-sm border border-cx-border-soft bg-cx-well p-3">
            <span class="block text-[11px] text-cx-ink-3">Package</span>
            <strong class="text-cx-ink">{{ req.package?.display_name || 'Not selected' }}</strong>
            <span v-if="req.package?.token_quantity" class="mt-0.5 block text-[11px] text-cx-ink-3">
              <CxIcon name="coins" class="inline-block size-4 align-[-0.15em]" /> {{ req.package.token_quantity }} tokens
            </span>
          </div>
          <div class="rounded-cx-sm border border-cx-border-soft bg-cx-well p-3">
            <span class="block text-[11px] text-cx-ink-3">Orders &amp; Invoices</span>
            <strong class="text-cx-ink">{{ req.open_orders }} open · {{ req.open_invoices }} due</strong>
          </div>
          <div class="rounded-cx-sm border border-cx-border-soft bg-cx-well p-3">
            <span class="block text-[11px] text-cx-ink-3">Quotations</span>
            <span v-if="!req.quotes.length" class="font-semibold text-cx-ink-4">None</span>
            <span v-else class="font-mono text-[11px] font-semibold text-cx-ink">{{ req.quotes.join(' · ') }}</span>
          </div>
        </div>
      </article>
    </div>
  </div>
</template>
