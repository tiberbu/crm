<template>
  <div class="mx-auto w-full max-w-sm px-4 py-8 text-center">
    <!-- Animated spinner while in progress -->
    <div v-if="overall !== 'complete' && overall !== 'failed'" class="mb-6 flex justify-center">
      <div
        class="h-12 w-12 animate-spin rounded-full border-4 border-gray-200 border-t-transparent"
        :style="{ borderTopColor: 'var(--brand-primary)' }"
      />
    </div>
    <!-- Success icon -->
    <div v-else-if="overall === 'complete'" class="mb-6 flex justify-center">
      <div
        class="flex h-14 w-14 items-center justify-center rounded-full"
        style="background-color: var(--brand-primary)"
      >
        <svg class="h-7 w-7 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </div>
    </div>
    <!-- Error icon -->
    <div v-else-if="overall === 'failed'" class="mb-6 flex justify-center">
      <div class="flex h-14 w-14 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30">
        <svg class="h-7 w-7 text-red-600 dark:text-red-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="8" x2="12" y2="12"/>
          <line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
      </div>
    </div>

    <h2 class="mb-2 text-xl font-bold text-gray-900 dark:text-white">
      <span v-if="overall === 'complete'">All done!</span>
      <span v-else-if="overall === 'failed'">Something went wrong</span>
      <span v-else>Setting things up...</span>
    </h2>

    <p class="mb-8 text-sm text-gray-500 dark:text-gray-400">
      <span v-if="overall !== 'failed'">This usually takes a few seconds.</span>
      <span v-else>{{ failureMessage }}</span>
    </p>

    <button
      v-if="overall === 'failed' && submissionRef"
      :disabled="retrying"
      class="mb-6 rounded-xl px-5 py-2.5 text-sm font-semibold text-white transition-opacity disabled:opacity-50"
      style="background-color: var(--brand-primary)"
      @click="retrySubmission"
    >
      <span v-if="retrying">Retrying...</span>
      <span v-else>Try Again</span>
    </button>

    <!-- Step list -->
    <div class="mb-8 text-left">
      <div
        v-for="step in displaySteps"
        :key="step.name"
        class="flex items-center gap-3 py-2"
      >
        <!-- Status icon -->
        <div class="flex-shrink-0">
          <div v-if="step.status === 'done'" class="flex h-6 w-6 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
            <svg class="h-3.5 w-3.5 text-green-600 dark:text-green-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </div>
          <div v-else-if="step.status === 'failed'" class="flex h-6 w-6 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30">
            <svg class="h-3.5 w-3.5 text-red-600 dark:text-red-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
              <line x1="7" y1="7" x2="17" y2="17" />
              <line x1="17" y1="7" x2="7" y2="17" />
            </svg>
          </div>
          <div v-else-if="step.status === 'in_progress'" class="flex h-6 w-6 items-center justify-center rounded-full" :style="{ backgroundColor: 'color-mix(in srgb, var(--brand-primary) 15%, transparent)' }">
            <div class="h-3.5 w-3.5 animate-spin rounded-full border-2 border-gray-200 border-t-transparent" :style="{ borderTopColor: 'var(--brand-primary)' }" />
          </div>
          <div v-else class="flex h-6 w-6 items-center justify-center rounded-full bg-gray-100 dark:bg-gray-800">
            <div class="h-2 w-2 rounded-full bg-gray-300 dark:bg-gray-600" />
          </div>
        </div>

        <span
          :class="[
            'text-sm',
            step.status === 'done' ? 'font-medium text-gray-900 dark:text-white' : 'text-gray-400 dark:text-gray-500',
          ]"
        >
          {{ step.label }}
        </span>
      </div>
    </div>

    <p v-if="overall === 'failed' && submissionRef" class="text-center font-mono text-xs text-gray-400 dark:text-gray-500">
      Reference: {{ submissionRef }}
    </p>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { createResource } from 'frappe-ui'
import { useOptInStore } from './useOptInStore.js'

const props = defineProps({
  networkSlug: { type: String, required: true },
})

const emit = defineEmits(['complete'])

const store = useOptInStore()

const steps = ref([])
const overall = ref('in_progress')
const failureMessage = ref('')
const submissionRef = ref(store.submissionRef)
const retrying = ref(false)
let pollInterval = null
let consecutiveErrors = 0

// Static step definitions (always show all 4, status from API)
const STEP_DEFS = [
  { name: 'lead',  defaultLabel: 'Your details saved' },
  { name: 'deal',  defaultLabel: 'Creating your account...' },
  { name: 'quote', defaultLabel: 'Generating your quote' },
  { name: 'email', defaultLabel: 'Sending confirmation' },
]

const displaySteps = computed(() => {
  return STEP_DEFS.map(def => {
    const fromApi = steps.value.find(s => s.name === def.name)
    return {
      name: def.name,
      status: fromApi ? fromApi.status : 'pending',
      label: fromApi ? fromApi.label : def.defaultLabel,
    }
  })
})

const statusResource = createResource({ url: 'crm.api.optin.get_job_status' })
const retryResource = createResource({ url: 'crm.api.optin.retry_public_submission' })

function stopPolling() {
  if (pollInterval) clearInterval(pollInterval)
  pollInterval = null
}

async function poll() {
  try {
    const data = await statusResource.fetch({
      submission_ref: store.submissionRef,
      signing_token: store.signingToken,
      email: store.contact.email,
      network_slug: props.networkSlug,
      expiry: store.signingExpiry,
    })
    steps.value = data.steps || []
    overall.value = data.overall || 'in_progress'
    failureMessage.value = data.message || ''
    submissionRef.value = data.submission_ref || store.submissionRef
    consecutiveErrors = 0

    if (data.overall === 'complete') {
      stopPolling()
      emit('complete')
    } else if (data.overall === 'failed') {
      stopPolling()
    }
  } catch {
    consecutiveErrors++
    if (consecutiveErrors >= 5) {
      stopPolling()
      overall.value = 'failed'
      failureMessage.value = 'We could not confirm the submission status. Please try again.'
    }
  }
}

async function retrySubmission() {
  retrying.value = true
  failureMessage.value = ''
  overall.value = 'in_progress'
  steps.value = []
  try {
    await retryResource.fetch({
      signing_token: store.signingToken,
      email: store.contact.email,
      network_slug: props.networkSlug,
      expiry: store.signingExpiry,
      submission_ref: submissionRef.value,
    })
    stopPolling()
    pollInterval = setInterval(poll, 3500)
    await poll()
  } catch (err) {
    overall.value = 'failed'
    failureMessage.value = err?.message || 'We could not retry this submission. Please contact support.'
  } finally {
    retrying.value = false
  }
}

onMounted(() => {
  poll()
  pollInterval = setInterval(poll, 3500)
})

onUnmounted(() => {
  stopPolling()
})
</script>
