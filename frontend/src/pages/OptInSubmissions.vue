<template>
  <div class="flex h-full flex-col overflow-hidden">
    <!-- Header -->
    <div
      class="flex items-center justify-between border-b border-outline-gray-2 px-5 py-3"
    >
      <h1 class="text-xl font-semibold text-ink-gray-9">
        {{ __('Opt-In Requests') }}
      </h1>
    </div>

    <!-- Status filter chips -->
    <div
      class="flex flex-wrap items-center gap-2 border-b border-outline-gray-2 px-5 py-2.5"
    >
      <button
        v-for="s in statuses"
        :key="s"
        :class="[
          'rounded-full px-3 py-1 text-xs font-medium transition-colors',
          selectedStatus === s
            ? 'bg-red-600 text-white'
            : 'bg-surface-gray-2 text-ink-gray-6 hover:bg-surface-gray-3 dark:bg-surface-gray-4 dark:text-ink-gray-4 dark:hover:bg-surface-gray-5',
        ]"
        @click="setStatus(s)"
      >
        {{ __(s) }}
      </button>
    </div>

    <div class="flex flex-wrap items-end gap-2 border-b border-outline-gray-2 px-5 py-3">
      <label class="flex flex-col gap-1 text-xs font-medium text-ink-gray-6">
        {{ __('Network') }}
        <select
          v-model="selectedNetwork"
          class="h-8 min-w-36 rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-8 dark:bg-surface-gray-3 dark:text-ink-gray-3"
          @change="applyFilters"
        >
          <option value="">{{ __('All networks') }}</option>
          <option v-for="network in filterNetworks" :key="network" :value="network">
            {{ network }}
          </option>
        </select>
      </label>
      <label class="flex flex-col gap-1 text-xs font-medium text-ink-gray-6">
        {{ __('Facility level') }}
        <select
          v-model="selectedFacilityLevel"
          class="h-8 min-w-32 rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-8 dark:bg-surface-gray-3 dark:text-ink-gray-3"
          @change="applyFilters"
        >
          <option value="">{{ __('All levels') }}</option>
          <option v-for="level in filterFacilityLevels" :key="level" :value="level">
            {{ level }}
          </option>
        </select>
      </label>
      <label class="flex flex-col gap-1 text-xs font-medium text-ink-gray-6">
        {{ __('Facility') }}
        <input
          v-model="facilitySearch"
          class="h-8 w-48 rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-8 dark:bg-surface-gray-3 dark:text-ink-gray-3"
          :placeholder="__('Facility name or MFL code')"
          @keyup.enter="applyFilters"
        />
      </label>
      <Button size="sm" variant="subtle" @click="applyFilters">{{ __('Apply') }}</Button>
      <Button size="sm" variant="ghost" @click="clearFilters">{{ __('Clear') }}</Button>
    </div>

    <!-- Table -->
    <div class="flex-1 overflow-auto">
      <div
        v-if="listResource.loading"
        class="flex items-center justify-center py-16"
      >
        <div
          class="h-6 w-6 animate-spin rounded-full border-2 border-red-600 border-t-transparent"
        />
      </div>

      <div
        v-else-if="!rows.length"
        class="flex flex-col items-center justify-center py-16 text-center"
      >
        <p class="text-sm font-medium text-ink-gray-5">
          {{ __('No submissions found') }}
        </p>
        <p class="mt-1 text-xs text-ink-gray-4">
          {{ __('Try adjusting your filters.') }}
        </p>
      </div>

      <table v-else class="w-full text-sm">
        <thead
          class="sticky top-0 z-10 bg-surface-gray-1 text-xs uppercase tracking-wide text-ink-gray-5"
        >
          <tr>
            <th class="px-5 py-2.5 text-left font-medium">{{ __('Ref #') }}</th>
            <th class="px-4 py-2.5 text-left font-medium">
              {{ __('Network') }}
            </th>
            <th class="px-4 py-2.5 text-left font-medium">
              {{ __('Submitter') }}
            </th>
            <th class="px-4 py-2.5 text-left font-medium">
              {{ __('Submitted') }}
            </th>
            <th class="px-4 py-2.5 text-left font-medium">{{ __('Lead') }}</th>
            <th class="px-4 py-2.5 text-left font-medium">{{ __('Deal') }}</th>
            <th class="px-4 py-2.5 text-left font-medium">
              {{ __('Status') }}
            </th>
            <th class="px-4 py-2.5 text-left font-medium">
              {{ __('Facility signing') }}
            </th>
            <th class="px-4 py-2.5 text-left font-medium">
              {{ __('Email delivery') }}
            </th>
            <th class="px-4 py-2.5 text-left font-medium">
              {{ __('Actions') }}
            </th>
          </tr>
        </thead>
        <tbody class="divide-y divide-outline-elevation-2">
          <tr
            v-for="row in rows"
            :key="row.name"
            :class="[
              'transition-colors',
              row.deal
                ? 'cursor-pointer hover:bg-surface-gray-1'
                : 'cursor-default',
            ]"
            @click="openDeal(row)"
          >
            <td class="px-5 py-3 font-medium text-ink-gray-9">
              {{ row.name }}
            </td>
            <td class="px-4 py-3 text-ink-gray-7">
              {{ row.network_slug || '—' }}
            </td>
            <td class="px-4 py-3 text-ink-gray-6 text-xs">
              {{ row.submitter_email || '—' }}
            </td>
            <td class="px-4 py-3 text-xs text-ink-gray-6">
              {{ formatDate(row.submitted_at) }}
            </td>
            <td class="px-4 py-3 text-xs text-ink-gray-6">
              {{ row.lead || '—' }}
            </td>
            <td class="px-4 py-3 text-xs text-ink-gray-6">
              {{ row.deal || '—' }}
            </td>
            <td class="px-4 py-3">
              <div class="flex flex-wrap items-center gap-1.5">
                <span :class="statusPill(row.status)">{{
                  __(row.status)
                }}</span>
                <span
                  v-if="row.has_duplicate_mfl"
                  class="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
                  >{{ __('Duplicate MFL') }}</span
                >
                <p
                  v-if="row.failure_reason"
                  class="w-full text-xs text-ink-red-6"
                  :title="row.failure_reason"
                >
                  {{ row.failure_reason }}
                </p>
              </div>
            </td>
            <td class="px-4 py-3">
              <div class="flex flex-col items-start gap-1">
                <div class="flex items-center gap-1.5">
                  <span class="text-xs text-ink-gray-5">{{ __('Signatory') }}</span>
                  <span :class="contractSigningPill(row.facility_signing_status)">
                    {{ __(row.facility_signing_status) }}
                  </span>
                </div>
                <span
                  v-if="row.facility_signatory_signed_at"
                  class="text-xs text-ink-gray-5"
                  >{{ formatDate(row.facility_signatory_signed_at) }}</span
                >
                <div class="flex items-center gap-1.5">
                  <span class="text-xs text-ink-gray-5">{{ __('Witness') }}</span>
                  <span :class="contractSigningPill(row.facility_witness_signing_status)">
                    {{ __(row.facility_witness_signing_status) }}
                  </span>
                </div>
                <span
                  v-if="row.facility_witness_signed_at"
                  class="text-xs text-ink-gray-5"
                  >{{ formatDate(row.facility_witness_signed_at) }}</span
                >
              </div>
            </td>
            <td class="px-4 py-3">
              <div class="flex flex-col items-start gap-1">
                <span
                  :class="emailStatusPill(row.confirmation_email_status)"
                  :title="emailStatusHint(row.confirmation_email_status)"
                  >{{ __('Confirmation') }}:
                  {{ emailStatusLabel(row.confirmation_email_status) }}</span
                >
                <span
                  v-if="row.confirmation_email_queued_at"
                  class="text-xs text-ink-gray-5"
                  >{{ formatDate(row.confirmation_email_queued_at) }}</span
                >
                <span
                  :class="emailStatusPill(row.contract_invitation_email_status)"
                  :title="emailStatusHint(row.contract_invitation_email_status)"
                  >{{ __('Contract') }}:
                  {{ emailStatusLabel(row.contract_invitation_email_status) }}</span
                >
                <span
                  v-if="row.contract_invitation_queued_at"
                  class="text-xs text-ink-gray-5"
                  >{{ formatDate(row.contract_invitation_queued_at) }}</span
                >
              </div>
            </td>
            <td class="px-4 py-3" @click.stop>
              <Button
                v-if="row.status === 'Failed'"
                size="sm"
                variant="subtle"
                :loading="retrying === row.name"
                @click="retry(row)"
                >{{ __('Retry') }}</Button
              >
            </td>
          </tr>
        </tbody>
      </table>

      <!-- Pagination -->
      <div
        v-if="total > pageSize"
        class="flex items-center justify-between border-t border-outline-gray-2 px-5 py-3"
      >
        <span class="text-xs text-ink-gray-5">
          {{
            __('Showing {0}–{1} of {2}', [
              page * pageSize + 1,
              Math.min((page + 1) * pageSize, total),
              total,
            ])
          }}
        </span>
        <div class="flex gap-2">
          <Button
            size="sm"
            variant="subtle"
            :disabled="page === 0"
            @click="page--"
            >{{ __('Prev') }}</Button
          >
          <Button
            size="sm"
            variant="subtle"
            :disabled="(page + 1) * pageSize >= total"
            @click="page++"
            >{{ __('Next') }}</Button
          >
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { createResource, Button } from 'frappe-ui'
import { useRouter } from 'vue-router'

const router = useRouter()

const statuses = ['All', 'Pending', 'Processing', 'Processed', 'Failed']
const selectedStatus = ref('All')
const selectedNetwork = ref('')
const selectedFacilityLevel = ref('')
const facilitySearch = ref('')
const page = ref(0)
const pageSize = 20
const retrying = ref(null)

function setStatus(s) {
  selectedStatus.value = s
  page.value = 0
  listResource.reload()
}

watch(page, () => listResource.reload())

const listResource = createResource({
  url: 'crm.api.optin.list_submissions',
  makeParams: () => ({
    status: selectedStatus.value === 'All' ? null : selectedStatus.value,
    network_slug: selectedNetwork.value || null,
    facility_level: selectedFacilityLevel.value || null,
    facility: facilitySearch.value || null,
    page: page.value,
    page_size: pageSize,
  }),
  auto: true,
})

const filtersResource = createResource({
  url: 'crm.api.optin.get_submission_filter_options',
  auto: true,
})

const rows = computed(() => listResource.data?.rows ?? [])
const total = computed(() => listResource.data?.total ?? 0)
const filterNetworks = computed(() => filtersResource.data?.networks ?? [])
const filterFacilityLevels = computed(
  () => filtersResource.data?.facility_levels ?? [],
)

function applyFilters() {
  page.value = 0
  listResource.reload()
}

function clearFilters() {
  selectedStatus.value = 'All'
  selectedNetwork.value = ''
  selectedFacilityLevel.value = ''
  facilitySearch.value = ''
  applyFilters()
}

const retryResource = createResource({ url: 'crm.api.optin.retry_submission' })

async function retry(row) {
  retrying.value = row.name
  try {
    await retryResource.submit({ submission_ref: row.name })
    listResource.reload()
  } finally {
    retrying.value = null
  }
}

function openDeal(row) {
  if (!row.deal) return
  // An Opt-In review should open on the lightweight Deal activity view. Respecting
  // the last-used Deal tab here could immediately mount the quote editor, which
  // loads quote lines, price lists, and the catalogue before the reviewer asks
  // for them.
  router.push({ name: 'Deal', params: { dealId: row.deal }, hash: '#activity' })
}

function formatDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

function statusPill(status) {
  const base = 'rounded-full px-2 py-0.5 text-xs font-medium'
  const map = {
    Pending: `${base} bg-surface-gray-2 text-ink-gray-6 dark:bg-surface-gray-4 dark:text-ink-gray-4`,
    Processing: `${base} bg-surface-gray-3 text-ink-gray-8 dark:bg-surface-gray-5 dark:text-ink-gray-3`,
    Processed: `${base} bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400`,
    Failed: `${base} bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400`,
  }
  return map[status] ?? map.Pending
}

function emailStatusLabel(status) {
  const map = {
    'Not queued': __('Not queued'),
    'Not tracked': __('Not tracked'),
    'Not Sent': __('Queued'),
    Sending: __('Sending'),
    Sent: __('Accepted'),
    'Partially Sent': __('Retrying'),
    Error: __('Failed'),
  }
  return map[status] ?? map['Not queued']
}

function emailStatusHint(status) {
  const map = {
    'Not queued': __('No email was queued.'),
    'Not tracked': __(
      'This existing contract was created before email delivery tracking was available.',
    ),
    'Not Sent': __('The email is queued for delivery.'),
    Sending: __('The email is being sent.'),
    Sent: __(
      'The email provider accepted this message. This does not confirm that the recipient opened it.',
    ),
    'Partially Sent': __('The email is being retried.'),
    Error: __(
      'The email provider could not send this message after its retries.',
    ),
  }
  return map[status] ?? map['Not queued']
}

function emailStatusPill(status) {
  const base = 'rounded-full px-2 py-0.5 text-xs font-medium'
  const map = {
    'Not queued': `${base} bg-surface-gray-2 text-ink-gray-6 dark:bg-surface-gray-4 dark:text-ink-gray-4`,
    'Not tracked': `${base} bg-surface-gray-2 text-ink-gray-6 dark:bg-surface-gray-4 dark:text-ink-gray-4`,
    'Not Sent': `${base} bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400`,
    Sending: `${base} bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400`,
    Sent: `${base} bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400`,
    'Partially Sent': `${base} bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400`,
    Error: `${base} bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400`,
  }
  return map[status] ?? map['Not queued']
}

function contractSigningPill(status) {
  const base = 'rounded-full px-2 py-0.5 text-xs font-medium'
  const map = {
    'Not generated': `${base} bg-surface-gray-2 text-ink-gray-6 dark:bg-surface-gray-4 dark:text-ink-gray-4`,
    'Preparing invitation': `${base} bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400`,
    'Awaiting signature': `${base} bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400`,
    Signed: `${base} bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400`,
    Declined: `${base} bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400`,
    'Signing link expired': `${base} bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400`,
    'Waiting for facility signatory': `${base} bg-surface-gray-2 text-ink-gray-6 dark:bg-surface-gray-4 dark:text-ink-gray-4`,
    'Blocked by declined signatory': `${base} bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400`,
    'Not required': `${base} bg-surface-gray-2 text-ink-gray-6 dark:bg-surface-gray-4 dark:text-ink-gray-4`,
  }
  return map[status] ?? map['Not generated']
}
</script>
