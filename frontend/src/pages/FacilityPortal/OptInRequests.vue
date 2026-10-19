<script setup>
defineProps({
  requests: { type: Array, required: true },
})
</script>

<template>
  <div>
    <div>
      <h1 class="text-4xl font-bold text-slate-900 tracking-tight leading-tight">Opt-In Requests</h1>
      <p class="text-xs text-slate-600 mt-0.5">Your network opt-in submissions, quotations, and enrollment progress in one place.</p>
    </div>

    <div v-if="!requests.length" class="mt-6 rounded-2xl border border-slate-200 bg-white p-10 text-center text-xs text-slate-500">
      <span class="mb-2 block text-3xl">📝</span>
      <p class="text-sm font-semibold text-slate-800">No opt-in requests</p>
      <p class="mt-1">You have no opt-in submissions with your network partner.</p>
    </div>

    <div v-else class="space-y-4 mt-6">
      <article
        v-for="req in requests"
        :key="req.name"
        class="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs"
      >
        <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <span class="font-semibold text-sm text-slate-900">{{ req.network }}</span>
              <span class="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-[11px] font-semibold text-slate-700">
                {{ req.status }}
              </span>
              <span v-if="req.contract" class="font-mono text-[11px] text-slate-500">Contract: {{ req.contract }}</span>
            </div>
            <p class="mt-1 text-[11px] text-slate-500">
              {{ req.name }}
              <span v-if="req.signatory"> · Signatory: {{ req.signatory }}</span>
            </p>
          </div>
          <span class="shrink-0 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-semibold text-slate-700">
            {{ req.facilities.length }} {{ req.facilities.length === 1 ? 'facility' : 'facilities' }}
          </span>
        </div>

        <div v-if="req.facilities.length" class="grid gap-2 sm:grid-cols-2">
          <div
            v-for="fac in req.facilities"
            :key="fac.mfl_code"
            class="flex items-center justify-between rounded-xl border border-slate-100 bg-slate-50 px-3 py-2 text-xs"
          >
            <span class="truncate font-semibold text-slate-800">🏥 {{ fac.name }}</span>
            <span class="ml-2 shrink-0 font-mono text-[11px] text-slate-500">{{ fac.mfl_code }}</span>
          </div>
        </div>

        <div class="grid gap-3 text-xs sm:grid-cols-3">
          <div class="rounded-xl border border-slate-100 bg-slate-50 p-3">
            <span class="block text-[11px] text-slate-500">Package</span>
            <strong class="text-slate-900">{{ req.package?.display_name || 'Not selected' }}</strong>
            <span v-if="req.package?.token_quantity" class="mt-0.5 block text-[11px] text-slate-600">
              🪙 {{ req.package.token_quantity }} tokens
            </span>
          </div>
          <div class="rounded-xl border border-slate-100 bg-slate-50 p-3">
            <span class="block text-[11px] text-slate-500">Orders &amp; Invoices</span>
            <strong class="text-slate-900">{{ req.open_orders }} open · {{ req.open_invoices }} due</strong>
          </div>
          <div class="rounded-xl border border-slate-100 bg-slate-50 p-3">
            <span class="block text-[11px] text-slate-500">Quotations</span>
            <span v-if="!req.quotes.length" class="font-semibold text-slate-400">None</span>
            <span v-else class="font-mono text-[11px] font-semibold text-slate-900">{{ req.quotes.join(' · ') }}</span>
          </div>
        </div>
      </article>
    </div>
  </div>
</template>
