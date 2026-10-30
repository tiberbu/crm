<script setup>
// Owner-managed low-token email alert for one facility (crm.api.token_alerts).
import { computed, ref, watch } from 'vue'
import { call } from 'frappe-ui'
import CxIcon from './CxIcon.vue'
import { facilityId } from '@/utils/facilityId'
import { tokenBalance } from '@/utils/tokenBalance'

const DEFAULT_THRESHOLD = 1000

const props = defineProps({
  facility: { type: Object, required: true },
  alert: { type: Object, default: null },
})
const emit = defineEmits(['saved'])

const enabled = ref(false)
const threshold = ref(DEFAULT_THRESHOLD)
const busy = ref(false)
const status = ref(null) // { tone: 'success' | 'info' | 'error', text }

function reset() {
  enabled.value = Boolean(props.alert?.enabled)
  threshold.value = props.alert?.threshold || DEFAULT_THRESHOLD
}
watch(() => props.alert, reset, { immediate: true })
watch(
  () => props.facility.mfl_code,
  () => {
    status.value = null
    reset()
  },
)

const fid = computed(() => facilityId(props.facility))
const balance = computed(() => tokenBalance(props.facility))
const thresholdValid = computed(
  () =>
    Number.isInteger(Number(threshold.value)) && Number(threshold.value) >= 1,
)
const changed = computed(
  () =>
    enabled.value !== Boolean(props.alert?.enabled) ||
    (enabled.value &&
      Number(threshold.value) !== Number(props.alert?.threshold || 0)),
)
const canSave = computed(
  () =>
    fid.value &&
    changed.value &&
    !busy.value &&
    (!enabled.value || thresholdValid.value),
)

function tokens(value) {
  return `${Number(value).toLocaleString()} ${Number(value) === 1 ? 'token' : 'tokens'}`
}

function savedMessage(result) {
  const limit = tokens(result.alert.threshold)
  if (!result.alert.enabled)
    return {
      tone: 'info',
      text: 'Alert turned off. You will not get low-token emails for this facility.',
    }
  if (result.alert_sent)
    return {
      tone: 'success',
      text: `Saved. Tokens are already at or below ${limit}, so we have emailed you now.`,
    }
  if (result.balance_status === 'ok')
    return {
      tone: 'success',
      text: `Saved. We will email you when tokens drop to ${limit} or below.`,
    }
  return {
    tone: 'info',
    text: `Saved. The live balance is not reported yet; we will email you once it is at or below ${limit}.`,
  }
}

async function save() {
  if (!canSave.value) return
  busy.value = true
  status.value = null
  try {
    const result = await call('crm.api.token_alerts.save_token_alert', {
      mfl_code: props.facility.mfl_code,
      enabled: enabled.value ? 1 : 0,
      threshold: Number(threshold.value),
    })
    status.value = savedMessage(result)
    emit('saved', result.alert)
  } catch (error) {
    status.value = {
      tone: 'error',
      text:
        error?.messages?.[0] ||
        error?.message ||
        'The alert could not be saved. Try again.',
    }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section
    class="rounded-cx border border-cx-border bg-cx-surface p-5 shadow-cx"
    data-testid="token-alert-card"
    aria-labelledby="token-alert-title"
  >
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0">
        <h2
          id="token-alert-title"
          class="flex items-center gap-1.5 text-sm font-semibold text-cx-ink"
        >
          <CxIcon name="bell" class="size-4 shrink-0" /> Low-token email alert
        </h2>
        <p class="mt-1 text-xs leading-relaxed text-cx-ink-3">
          Get an email when this facility's available tokens drop to a level you
          choose, so you can top up before clinical work stops.
        </p>
      </div>
      <label
        class="inline-flex shrink-0 cursor-pointer items-center gap-2 text-xs font-semibold text-cx-ink-2"
        :class="!fid && 'cursor-not-allowed opacity-60'"
      >
        <input
          v-model="enabled"
          type="checkbox"
          role="switch"
          class="peer sr-only"
          :aria-checked="enabled"
          :disabled="!fid || busy"
          data-testid="token-alert-toggle"
        />
        <span
          class="relative h-5 w-9 rounded-full transition peer-focus-visible:ring-2 peer-focus-visible:ring-cx-brand peer-focus-visible:ring-offset-2"
          :class="enabled ? 'bg-cx-brand' : 'bg-cx-border'"
          aria-hidden="true"
        >
          <span
            class="absolute left-0.5 top-0.5 size-4 rounded-full bg-white shadow transition"
            :class="enabled && 'translate-x-4'"
          ></span>
        </span>
        {{ enabled ? 'On' : 'Off' }}
      </label>
    </div>

    <p
      v-if="!fid"
      class="mt-3 rounded-cx-sm border border-cx-border-soft bg-cx-well p-3 text-xs text-cx-ink-2"
    >
      Alerts need the facility's HFR Facility ID, because live balances are
      tracked by Facility ID. Link the facility to the registry first.
    </p>

    <div v-else-if="enabled" class="mt-4 flex flex-wrap items-end gap-3">
      <div class="min-w-0">
        <label
          for="token-alert-threshold"
          class="block text-xs font-semibold text-cx-ink-2"
          >Email me when tokens reach</label
        >
        <div class="mt-1 flex items-center gap-2">
          <input
            id="token-alert-threshold"
            v-model.number="threshold"
            type="number"
            inputmode="numeric"
            min="1"
            step="1"
            class="w-36 rounded-cx-sm border border-cx-border bg-cx-surface px-3 py-2 text-sm font-semibold text-cx-ink focus:border-cx-brand focus:outline-none focus:ring-1 focus:ring-cx-brand"
            :aria-invalid="!thresholdValid"
            aria-describedby="token-alert-context"
            data-testid="token-alert-threshold"
            @keydown.enter.prevent="save"
          />
          <span class="text-xs text-cx-ink-3">tokens or fewer</span>
        </div>
      </div>
    </div>

    <p id="token-alert-context" v-if="fid" class="mt-3 text-xs text-cx-ink-3">
      <template v-if="balance.known"
        >Available now:
        <strong class="text-cx-ink-2">{{ tokens(balance.value) }}</strong
        >.</template
      >
      <template v-else
        >The live balance is not reported right now. No email is sent until it
        is, so an outage is never reported as an empty balance.</template
      >
      <template v-if="alert?.alert_sent_at">
        Last alert sent
        {{ new Date(alert.alert_sent_at).toLocaleString() }}.</template
      >
    </p>
    <p
      v-if="enabled && !thresholdValid"
      class="mt-2 text-xs font-semibold text-cx-danger-ink"
    >
      Enter a whole number of 1 or more.
    </p>

    <div v-if="fid" class="mt-4 flex flex-wrap items-center gap-3">
      <button
        type="button"
        class="rounded-cx-sm bg-cx-ink px-4 py-2 text-xs font-semibold text-cx-contrast transition hover:bg-cx-ink-hover disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="!canSave"
        data-testid="token-alert-save"
        @click="save"
      >
        {{ busy ? 'Saving…' : 'Save alert' }}
      </button>
      <p
        v-if="status"
        class="min-w-0 flex-1 text-xs"
        :class="{
          'text-cx-success-ink': status.tone === 'success',
          'text-cx-ink-2': status.tone === 'info',
          'text-cx-danger-ink': status.tone === 'error',
        }"
        :role="status.tone === 'error' ? 'alert' : 'status'"
        data-testid="token-alert-status"
      >
        {{ status.text }}
      </p>
    </div>
  </section>
</template>
