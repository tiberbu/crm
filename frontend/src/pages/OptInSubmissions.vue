<template>
  <div class="flex h-full flex-col overflow-hidden">
    <!-- Header -->
    <div
      class="flex items-center justify-between border-b border-outline-gray-2 px-3 py-3 sm:px-5"
    >
      <h1 class="text-xl font-semibold text-ink-gray-9">
        {{ __('Opt-In Requests') }}
      </h1>
    </div>

    <!-- Status filter chips -->
    <div
      class="flex flex-nowrap items-center gap-2 overflow-x-auto border-b border-outline-gray-2 px-3 py-2.5 sm:flex-wrap sm:px-5"
    >
      <button
        type="button"
        :class="[
          'shrink-0 rounded-full border px-3 py-1 text-xs font-semibold transition-colors',
          pendingMyAction
            ? 'border-red-600 bg-red-600 text-white'
            : 'border-red-200 bg-red-50 text-red-700 hover:bg-red-100 dark:border-red-900 dark:bg-red-900/20 dark:text-red-300',
        ]"
        @click="togglePendingMyAction"
      >
        {{ __('Pending my action') }}
      </button>
      <button
        v-for="s in statuses"
        :key="s"
        :class="[
          'shrink-0 rounded-full px-3 py-1 text-xs font-medium transition-colors',
          selectedStatus === s
            ? 'bg-red-600 text-white'
            : 'bg-surface-gray-2 text-ink-gray-6 hover:bg-surface-gray-3 dark:bg-surface-gray-4 dark:text-ink-gray-4 dark:hover:bg-surface-gray-5',
        ]"
        @click="setStatus(s)"
      >
        {{ __(s) }}
      </button>
    </div>

    <div
      class="grid grid-cols-2 gap-2 border-b border-outline-gray-2 px-3 py-3 sm:flex sm:flex-wrap sm:items-end sm:px-5"
    >
      <label
        class="col-span-1 flex min-w-0 flex-col gap-1 text-xs font-medium text-ink-gray-6"
      >
        {{ __('Network') }}
        <select
          v-model="selectedNetwork"
          class="h-8 w-full min-w-0 rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-8 dark:bg-surface-gray-3 dark:text-ink-gray-3 sm:w-auto sm:min-w-36"
          @change="applyFilters"
        >
          <option value="">{{ __('All networks') }}</option>
          <option
            v-for="network in filterNetworks"
            :key="network"
            :value="network"
          >
            {{ network }}
          </option>
        </select>
      </label>
      <label
        class="col-span-1 flex min-w-0 flex-col gap-1 text-xs font-medium text-ink-gray-6"
      >
        {{ __('Facility level') }}
        <select
          v-model="selectedFacilityLevel"
          class="h-8 w-full min-w-0 rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-8 dark:bg-surface-gray-3 dark:text-ink-gray-3 sm:w-auto sm:min-w-32"
          @change="applyFilters"
        >
          <option value="">{{ __('All levels') }}</option>
          <option
            v-for="level in filterFacilityLevels"
            :key="level"
            :value="level"
          >
            {{ level }}
          </option>
        </select>
      </label>
      <label
        class="col-span-2 flex min-w-0 flex-col gap-1 text-xs font-medium text-ink-gray-6 sm:col-span-1"
      >
        {{ __('Facility') }}
        <input
          v-model="facilitySearch"
          class="h-8 w-full min-w-0 rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-8 dark:bg-surface-gray-3 dark:text-ink-gray-3 sm:w-48"
          :placeholder="__('Facility name or MFL code')"
          @keyup.enter="applyFilters"
          @input="scheduleSearch"
        />
      </label>
      <div class="col-span-2 flex gap-2 sm:col-span-1">
        <Button
          class="flex-1 sm:flex-none"
          size="sm"
          variant="subtle"
          @click="applyFilters"
          >{{ __('Apply') }}</Button
        >
        <Button
          class="flex-1 sm:flex-none"
          size="sm"
          variant="ghost"
          @click="clearFilters"
          >{{ __('Clear') }}</Button
        >
      </div>
    </div>

    <!-- Table -->
    <div class="flex-1 overflow-auto">
      <div
        class="flex items-center justify-between border-b border-outline-gray-2 px-3 py-2 text-xs text-ink-gray-5 sm:px-5"
        aria-live="polite"
      >
        <span v-if="listResource.loading">{{ __('Updating results…') }}</span>
        <span v-else>{{ __('{0} results', [total]) }}</span>
        <span
          v-if="facilitySearch"
          class="max-w-[60%] truncate text-ink-gray-6"
        >
          {{ __('For “{0}”', [facilitySearch]) }}
        </span>
      </div>
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
            <th class="px-5 py-2.5 text-left font-medium">
              {{ __('Facility') }}
            </th>
            <th class="px-4 py-2.5 text-left font-medium">
              {{ __('Facility signing') }}
            </th>
            <th class="px-4 py-2.5 text-left font-medium">
              {{ __('Network signatories') }}
            </th>
            <th class="px-4 py-2.5 text-left font-medium">
              {{ __('Tiberbu signatory') }}
            </th>
            <th class="px-4 py-2.5 text-left font-medium">
              {{ __('Email delivery') }}
            </th>
            <th class="px-4 py-2.5 text-left font-medium">
              {{ __('Submission') }}
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
            <td class="px-5 py-3">
              <p class="font-medium text-ink-gray-9">
                {{ row.facility_name }}
              </p>
              <div class="mt-1 flex flex-wrap items-center gap-1.5">
                <span
                  v-if="row.facility_level"
                  class="rounded-full bg-surface-gray-2 px-2 py-0.5 text-xs font-medium text-ink-gray-7 dark:bg-surface-gray-4 dark:text-ink-gray-4"
                  >{{ row.facility_level }}</span
                >
                <span
                  v-if="row.facility_mfl_code"
                  class="text-xs text-ink-gray-5"
                >
                  {{ row.facility_mfl_code }}
                </span>
                <span
                  v-if="row.facility_count > 1"
                  class="text-xs text-ink-gray-5"
                >
                  {{ __('+{0} more', [row.facility_count - 1]) }}
                </span>
              </div>
              <p class="mt-1 text-xs text-ink-gray-5">
                {{ row.network_slug || '—' }}
              </p>
            </td>
            <td class="px-4 py-3">
              <div class="flex flex-col items-start gap-1">
                <p
                  v-if="row.facility_signatory_name"
                  class="text-xs font-medium text-ink-gray-8"
                >
                  {{ row.facility_signatory_name }}
                  <span class="font-normal text-ink-gray-5">
                    · {{ signatoryModeLabel(row) }}
                  </span>
                </p>
                <p class="text-xs text-ink-gray-5">
                  {{ __('Submitted by') }}:
                  {{ row.submitter_name || row.submitter_email || '—' }}
                </p>
                <div class="flex items-center gap-1.5">
                  <span class="text-xs text-ink-gray-5">{{
                    __('Signatory')
                  }}</span>
                  <span
                    :class="contractSigningPill(row.facility_signing_status)"
                  >
                    {{ __(row.facility_signing_status) }}
                  </span>
                </div>
                <span
                  v-if="row.facility_signatory_signed_at"
                  class="text-xs text-ink-gray-5"
                  >{{ formatDate(row.facility_signatory_signed_at) }}</span
                >
                <div class="flex items-center gap-1.5">
                  <span class="text-xs text-ink-gray-5">{{
                    __('Witness')
                  }}</span>
                  <span
                    :class="
                      contractSigningPill(row.facility_witness_signing_status)
                    "
                  >
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
            <td class="px-4 py-3 align-top">
              <div
                v-if="row.network_signatories?.length"
                class="flex min-w-52 flex-col gap-1.5"
              >
                <div
                  v-for="(signatory, index) in row.network_signatories"
                  :key="`${row.name}-network-${index}`"
                  class="flex flex-wrap items-center gap-1.5"
                >
                  <span class="text-xs font-medium text-ink-gray-8">
                    {{ signatory.name }}
                  </span>
                  <span :class="contractSigningPill(signatory.status)">
                    {{ __(signatory.status) }}
                  </span>
                  <span
                    v-if="signatory.signed_at"
                    class="w-full text-xs text-ink-gray-5"
                  >
                    {{ formatDate(signatory.signed_at) }}
                  </span>
                </div>
                <span class="text-xs font-medium text-ink-gray-6">
                  {{ signatorySummary(row.network_signatories) }}
                </span>
              </div>
              <span v-else class="text-xs text-ink-gray-5">
                {{ noSignatoryLabel(row) }}
              </span>
            </td>
            <td class="px-4 py-3 align-top">
              <div
                v-if="row.tiberbu_signatory"
                class="flex min-w-44 flex-col items-start gap-1"
              >
                <span class="text-xs font-medium text-ink-gray-8">
                  {{ row.tiberbu_signatory.name }}
                </span>
                <span
                  :class="contractSigningPill(row.tiberbu_signatory.status)"
                >
                  {{ __(row.tiberbu_signatory.status) }}
                </span>
                <span
                  v-if="row.tiberbu_signatory.signed_at"
                  class="text-xs text-ink-gray-5"
                >
                  {{ formatDate(row.tiberbu_signatory.signed_at) }}
                </span>
              </div>
              <span v-else class="text-xs text-ink-gray-5">
                {{ noSignatoryLabel(row) }}
              </span>
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
                  {{
                    emailStatusLabel(row.contract_invitation_email_status)
                  }}</span
                >
                <span
                  v-if="row.contract_invitation_queued_at"
                  class="text-xs text-ink-gray-5"
                  >{{ formatDate(row.contract_invitation_queued_at) }}</span
                >
              </div>
            </td>
            <td class="px-4 py-3">
              <div class="flex flex-col items-start gap-1.5">
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
                <p v-else class="text-xs text-ink-gray-5">
                  {{ formatDate(row.submitted_at) }} ·
                  {{ row.submitter_email || '—' }}
                </p>
                <p class="font-mono text-xs text-ink-gray-4">{{ row.name }}</p>
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
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { createResource, Button } from 'frappe-ui'
import { useRoute, useRouter } from 'vue-router'

const router = useRouter()
const route = useRoute()

const statuses = ['All', 'Pending', 'Processing', 'Processed', 'Failed']
const selectedStatus = ref('All')
const selectedNetwork = ref('')
const selectedFacilityLevel = ref('')
const facilitySearch = ref('')
const pendingMyAction = ref(route.query.pending_my_action === '1')
const page = ref(0)
const pageSize = 20
const retrying = ref(null)

function setStatus(s) {
  selectedStatus.value = s
  applyFilters()
}

watch(page, () => listResource.reload())

let searchTimer = null

function scheduleSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    searchTimer = null
    applyFilters()
  }, 300)
}

const listResource = createResource({
  url: 'crm.api.optin.list_submissions',
  makeParams: () => ({
    status: selectedStatus.value === 'All' ? null : selectedStatus.value,
    network_slug: selectedNetwork.value || null,
    facility_level: selectedFacilityLevel.value || null,
    facility: facilitySearch.value || null,
    pending_my_action: pendingMyAction.value ? 1 : 0,
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
  if (searchTimer) {
    clearTimeout(searchTimer)
    searchTimer = null
  }
  if (page.value !== 0) {
    page.value = 0
    return
  }
  listResource.reload()
}

onBeforeUnmount(() => {
  if (searchTimer) clearTimeout(searchTimer)
})

function togglePendingMyAction() {
  pendingMyAction.value = !pendingMyAction.value
  applyFilters()
}

function clearFilters() {
  selectedStatus.value = 'All'
  selectedNetwork.value = ''
  selectedFacilityLevel.value = ''
  facilitySearch.value = ''
  pendingMyAction.value = false
  applyFilters()
}

function signatorySummary(signatories) {
  const total = signatories?.length ?? 0
  const signed =
    signatories?.filter((signatory) => signatory.status === 'Signed').length ??
    0
  return __('{0} of {1} signed', [signed, total])
}

function noSignatoryLabel(row) {
  return row.contract ? __('Not configured') : __('Not generated')
}

function signatoryModeLabel(row) {
  return row.signatory_mode === 'delegate'
    ? __('Nominated signatory')
    : __('Submitter signs')
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
    'Included in signing package': __('Included in signing package'),
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
    'Included in signing package': __(
      'The submitter and signatory are the same person; the Opt-In summary is included in the signing package.',
    ),
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
    'Included in signing package': `${base} bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400`,
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
    'Not configured': `${base} bg-surface-gray-2 text-ink-gray-6 dark:bg-surface-gray-4 dark:text-ink-gray-4`,
    'Preparing invitation': `${base} bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400`,
    'Awaiting signature': `${base} bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400`,
    Signed: `${base} bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400`,
    Declined: `${base} bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400`,
    'Signing link expired': `${base} bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400`,
    'Review required': `${base} bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400`,
    'Waiting for facility signatory': `${base} bg-surface-gray-2 text-ink-gray-6 dark:bg-surface-gray-4 dark:text-ink-gray-4`,
    'Blocked by declined signatory': `${base} bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400`,
    'Not required': `${base} bg-surface-gray-2 text-ink-gray-6 dark:bg-surface-gray-4 dark:text-ink-gray-4`,
  }
  return map[status] ?? map['Not generated']
}
</script>
