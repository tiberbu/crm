<template>
  <div
    v-if="visible"
    class="mt-4 rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800"
  >
    <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Link your Facility ID</h3>

    <!-- Start: owner ID lookup -->
    <div v-if="phase === 'start'">
      <p class="mt-1 text-sm text-gray-600 dark:text-gray-300">
        Enter the facility owner's ID number to find the Facility ID in the Health Facility
        Registry. We use it once for this search and don't store it. You can skip this and
        continue.
      </p>
      <label class="mt-3 block text-xs font-medium text-gray-600 dark:text-gray-300">
        Owner ID number
        <input
          v-model="ownerId"
          type="text"
          autocomplete="off"
          class="mt-1 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm dark:border-gray-600 dark:bg-gray-800"
          :disabled="busy"
        />
      </label>
      <button
        type="button"
        class="mt-3 rounded-xl px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
        style="background-color: var(--brand-primary)"
        :disabled="busy || !ownerId.trim()"
        @click="findFacilities"
      >
        Find facilities
      </button>
    </div>

    <!-- Results -->
    <div v-else>
      <template v-if="status === 'ok'">
        <div v-for="facility in facilities" :key="facility.mfl_code" class="mt-3">
          <p class="text-sm font-medium text-gray-900 dark:text-white">
            {{ facility.facility_name }}
            <span class="text-xs font-normal text-gray-400 dark:text-gray-500">MFL {{ facility.mfl_code }}</span>
          </p>
          <div class="mt-1 flex flex-wrap items-center gap-2">
            <select
              :value="picked[facility.mfl_code] || ''"
              class="min-h-10 w-full max-w-xs rounded-md border border-gray-300 bg-white px-3 text-sm dark:border-gray-600 dark:bg-gray-800"
              :disabled="busy"
              @change="picked[facility.mfl_code] = $event.target.value"
            >
              <option value="">Choose a facility</option>
              <option v-for="candidate in availableCandidates" :key="candidate.candidate_id" :value="candidate.candidate_id">
                {{ candidateLabel(candidate) }}
              </option>
            </select>
            <button
              v-if="confirming !== facility.mfl_code"
              type="button"
              class="rounded-xl px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              style="background-color: var(--brand-primary)"
              :disabled="busy || !picked[facility.mfl_code]"
              @click="confirming = facility.mfl_code"
            >
              Link
            </button>
            <span v-else class="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-300">
              Link {{ facility.facility_name }} to {{ candidateName(picked[facility.mfl_code]) }}? You can't change this here.
              <button
                type="button"
                class="rounded-xl px-3 py-1.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                style="background-color: var(--brand-primary)"
                :disabled="busy"
                @click="linkFacility(facility)"
              >
                Yes, link it
              </button>
              <button
                type="button"
                class="rounded-xl border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-600 transition hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
                :disabled="busy"
                @click="confirming = ''"
              >
                Cancel
              </button>
            </span>
          </div>
        </div>
      </template>

      <p v-else class="mt-2 text-sm text-gray-600 dark:text-gray-300">{{ statusText }}</p>

      <button
        v-if="status !== 'ok'"
        type="button"
        class="mt-3 text-xs font-medium underline text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
        @click="reset"
      >
        Search again
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive } from 'vue'
import { call } from 'frappe-ui'
import { useOptInStore } from './useOptInStore.js'

const props = defineProps({
  facilities: { type: Array, default: () => [] },
  dealInvitation: { type: String, default: '' },
})

const emit = defineEmits(['linked'])

const store = useOptInStore()

const phase = ref('start')
const status = ref('')
const statusText = ref('')
const ownerId = ref('')
const busy = ref(false)
const candidates = ref([])
const linkedCandidateIds = reactive(new Set())
const picked = reactive({})
const confirming = ref('')

const visible = computed(() => phase.value === 'start' || status.value !== 'no_unlinked')

const availableCandidates = computed(() =>
  candidates.value.filter((candidate) => !linkedCandidateIds.has(candidate.candidate_id)),
)

function candidateLabel(candidate) {
  const bits = [candidate.facility_name]
  if (candidate.facility_level) bits.push(candidate.facility_level)
  if (candidate.facility_type) bits.push(candidate.facility_type)
  return bits.filter(Boolean).join(' · ')
}

function candidateName(candidateId) {
  const candidate = candidates.value.find((c) => c.candidate_id === candidateId)
  return candidate ? candidate.facility_name : ''
}

function callParams() {
  return {
    signing_token: store.signingToken,
    email: store.contact.email,
    network_slug: store.networkSlug,
    expiry: store.signingExpiry,
    deal_invitation: props.dealInvitation,
  }
}

async function findFacilities() {
  busy.value = true
  statusText.value = ''
  try {
    const result = await call('crm.api.optin.lookup_owner_facilities', {
      ...callParams(),
      owner_id_number: ownerId.value.trim(),
    })
    status.value = result.status
    candidates.value = result.candidates || []
    Object.keys(picked).forEach((key) => delete picked[key])
    phase.value = 'results'
    if (result.status !== 'ok') statusText.value = textFor(result.status)
  } catch (error) {
    status.value = 'unavailable'
    statusText.value = error?.messages?.[0] || textFor('unavailable')
    phase.value = 'results'
  } finally {
    ownerId.value = ''
    busy.value = false
  }
}

async function linkFacility(facility) {
  const candidateId = picked[facility.mfl_code]
  if (!candidateId) return
  busy.value = true
  try {
    const result = await call('crm.api.optin.link_facility_id', {
      ...callParams(),
      mfl_code: facility.mfl_code,
      candidate_id: candidateId,
    })
    if (result.status === 'linked') {
      store.setFacilityId(facility.mfl_code, result.hfr_facility_id)
      linkedCandidateIds.add(candidateId)
      delete picked[facility.mfl_code]
      confirming.value = ''
      emit('linked', facility.mfl_code)
      if (linkedCandidateIds.size >= candidates.value.length) phase.value = 'start'
    } else {
      status.value = result.status
      statusText.value = textFor(result.status)
      phase.value = 'results'
    }
  } catch (error) {
    status.value = 'unavailable'
    statusText.value = error?.messages?.[0] || textFor('unavailable')
    phase.value = 'results'
  } finally {
    busy.value = false
  }
}

function textFor(status) {
  const text = {
    no_facilities:
      "No facilities were found for that ID. Check the number, or continue and your network coordinator will link it.",
    invalid_id: 'Enter the ID number as it appears on the document.',
    unavailable:
      "The registry can't be reached right now. You can try again, or continue and your network coordinator will link it.",
    rate_limited: 'Too many searches. Continue and your network coordinator will link it.',
    needs_coordinator: 'This facility needs your network coordinator to link it. You can continue.',
    expired: 'That search has expired. Search again.',
    not_allowed: 'That search has expired. Search again.',
  }
  return text[status] || text.unavailable
}

function reset() {
  phase.value = 'start'
  status.value = ''
  statusText.value = ''
  candidates.value = []
  linkedCandidateIds.clear()
  Object.keys(picked).forEach((key) => delete picked[key])
  confirming.value = ''
}
</script>
