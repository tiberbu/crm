<script setup>
// Token usage report for one facility (P-135, docs/cx-facility-usage-report.md).
import { computed, ref, watch } from 'vue'
import { call } from 'frappe-ui'
import CxIcon from './CxIcon.vue'
import {
  SOURCES,
  checkLabel,
  checkSummary,
  checkTone,
  formatShare,
  formatTokens,
  usageDownloadUrl,
  usageRangeError,
  usageRangePresets,
} from '@/utils/usageReport'

const props = defineProps({
  mflCode: { type: String, required: true },
  fid: { type: String, required: true },
  facilityName: { type: String, default: '' },
})

const EVENT_PAGE = 50
const presets = usageRangePresets()
const preset = ref('last30')
const from = ref(presets[1].from)
const to = ref(presets[1].to)
const report = ref(null)
const state = ref('idle') // idle | loading | ok | error
const errorText = ref('')
const onlyFlagged = ref(false)
const eventLimit = ref(EVENT_PAGE)
let seq = 0

const rangeError = computed(() => usageRangeError(from.value, to.value))
const summary = computed(() => report.value?.summary || {})
const added = computed(() => summary.value.tokens_added || {})
const addedSources = computed(() =>
  Object.entries(added.value.in_range?.by_source || {}).map(([key, value]) => ({
    key,
    label: SOURCES[key] || key,
    value,
  })),
)
const detail = computed(() => report.value?.detail || {})
const checks = computed(() => checkSummary(summary.value.checks))
const flaggedCount = computed(() =>
  checks.value
    .filter((c) => c.key === 'price_differs' || c.key === 'charge_differs')
    .reduce((n, c) => n + c.count, 0),
)
const events = computed(() => {
  const rows = report.value?.events || []
  return onlyFlagged.value
    ? rows.filter(
        (row) =>
          row.check === 'price_differs' || row.check === 'charge_differs',
      )
    : rows
})
const visibleEvents = computed(() => events.value.slice(0, eventLimit.value))
const downloadUrl = computed(() =>
  // The range of the report on screen, not unapplied edits in the date fields.
  usageDownloadUrl(
    props.mflCode,
    report.value?.from_date || from.value,
    report.value?.to_date || to.value,
  ),
)
const cards = computed(() => [
  {
    key: 'added',
    label: 'Tokens added',
    value: formatTokens(added.value.in_range?.total || 0),
    note: `${formatTokens(added.value.all_time || 0)} since onboarding`,
  },
  {
    key: 'consumed',
    label: 'Tokens consumed',
    value: formatTokens(summary.value.tokens_consumed || 0),
    note: 'In the selected range',
  },
  {
    key: 'balance',
    label: 'Available now',
    value: formatTokens(summary.value.balance),
    note:
      summary.value.balance === null || summary.value.balance === undefined
        ? 'Live balance unavailable'
        : 'Live from metering',
  },
  {
    key: 'registrations',
    label: 'Patient registrations',
    value: formatTokens(summary.value.patient_registrations?.value || 0),
    note: summary.value.patient_registrations?.estimated
      ? 'Estimate from tokens ÷ current price'
      : `${formatTokens(summary.value.consultations?.value || 0)} consultations`,
  },
])

const TONE = {
  success: 'border-cx-success-border bg-cx-success-soft text-cx-success-ink',
  warning: 'border-cx-warning-border bg-cx-warning-soft text-cx-warning-ink',
  error: 'border-cx-danger-border bg-cx-danger-soft text-cx-danger-ink',
  neutral: 'border-cx-border bg-cx-well text-cx-ink-2',
}

function choosePreset(item) {
  preset.value = item.key
  from.value = item.from
  to.value = item.to
  load()
}

function onCustom() {
  preset.value = 'custom'
}

async function load() {
  if (rangeError.value) return
  const current = ++seq
  state.value = 'loading'
  errorText.value = ''
  eventLimit.value = EVENT_PAGE
  try {
    const result = await call(
      'crm.api.usage_report.get_facility_usage_report',
      {
        mfl_code: props.mflCode,
        from_date: from.value,
        to_date: to.value,
      },
    )
    if (current !== seq) return
    report.value = result?.message || result || null
    state.value = report.value?.status === 'ok' ? 'ok' : 'error'
    if (state.value === 'error') {
      errorText.value =
        report.value?.status === 'not_metered'
          ? 'Usage appears here once this facility starts using tokens in its HMIS.'
          : report.value?.status === 'disabled'
            ? 'Usage reporting is not switched on for this portal yet.'
            : 'We could not load usage right now. Please try again in a moment.'
    }
  } catch (error) {
    if (current !== seq) return
    state.value = 'error'
    errorText.value =
      error?.messages?.[0] ||
      'We could not load usage right now. Please try again in a moment.'
  }
}

watch(
  () => props.mflCode,
  () => load(),
  { immediate: true },
)
</script>

<template>
  <section class="space-y-5" data-testid="usage-report">
    <div
      class="rounded-cx border border-cx-border bg-cx-surface p-4 shadow-cx sm:p-5"
    >
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <p class="text-xs font-semibold text-cx-ink-3">Token usage report</p>
          <h3 class="mt-1 text-lg font-semibold text-cx-ink">
            {{ facilityName || 'This facility' }}
          </h3>
          <p class="mt-1 text-xs text-cx-ink-2">
            Facility ID
            <span class="font-mono font-semibold text-cx-ink">{{ fid }}</span>
            <template v-if="mflCode">
              · MFL code
              <span class="font-mono font-semibold text-cx-ink">{{
                mflCode
              }}</span></template
            >
          </p>
        </div>
        <a
          v-if="state === 'ok'"
          :href="downloadUrl"
          download
          class="inline-flex items-center gap-2 rounded-cx-sm bg-cx-brand px-3.5 py-2.5 text-xs font-semibold text-cx-contrast shadow-cx transition hover:bg-cx-brand-strong"
          data-testid="usage-download"
        >
          <CxIcon name="download" class="size-4" /> Download report (CSV)
        </a>
      </div>

      <div
        class="mt-4 flex flex-wrap gap-2"
        role="group"
        aria-label="Date range"
      >
        <button
          v-for="item in presets"
          :key="item.key"
          type="button"
          class="rounded-full border px-3 py-1.5 text-xs font-semibold transition"
          :class="
            preset === item.key
              ? 'border-cx-brand bg-cx-brand-soft text-cx-brand-ink'
              : 'border-cx-border bg-cx-surface text-cx-ink-2 hover:bg-cx-well'
          "
          :aria-pressed="preset === item.key"
          :data-testid="`usage-preset-${item.key}`"
          @click="choosePreset(item)"
        >
          {{ item.label }}
        </button>
      </div>
      <form class="mt-3 flex flex-wrap items-end gap-3" @submit.prevent="load">
        <label class="text-xs font-semibold text-cx-ink-3">
          From
          <input
            v-model="from"
            type="date"
            :max="to"
            class="mt-1 block rounded-cx-sm border-cx-border text-sm text-cx-ink"
            data-testid="usage-from"
            @input="onCustom"
          />
        </label>
        <label class="text-xs font-semibold text-cx-ink-3">
          To
          <input
            v-model="to"
            type="date"
            :min="from"
            class="mt-1 block rounded-cx-sm border-cx-border text-sm text-cx-ink"
            data-testid="usage-to"
            @input="onCustom"
          />
        </label>
        <button
          type="submit"
          class="rounded-cx-sm border border-cx-border bg-cx-surface px-3.5 py-2.5 text-xs font-semibold text-cx-ink transition hover:bg-cx-well disabled:opacity-60"
          :disabled="Boolean(rangeError) || state === 'loading'"
          data-testid="usage-apply"
        >
          {{ state === 'loading' ? 'Loading…' : 'Show usage' }}
        </button>
        <p v-if="rangeError" class="text-xs text-cx-warning-ink" role="alert">
          {{ rangeError }}
        </p>
      </form>
    </div>

    <div
      v-if="state === 'loading' && !report"
      class="rounded-cx-sm bg-cx-well p-4 text-sm text-cx-ink-2"
      aria-busy="true"
    >
      Loading usage…
    </div>
    <div
      v-else-if="state === 'error'"
      class="flex flex-wrap items-center justify-between gap-2 rounded-cx-sm border border-cx-warning-border bg-cx-warning-soft/60 p-4 text-sm text-cx-warning-ink"
      role="alert"
      data-testid="usage-error"
    >
      <span>{{ errorText }}</span>
      <button type="button" class="font-semibold underline" @click="load">
        Try again
      </button>
    </div>

    <template
      v-if="state === 'ok' || (state === 'loading' && report?.status === 'ok')"
    >
      <dl
        class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
        :aria-busy="state === 'loading'"
        data-testid="usage-summary"
      >
        <div
          v-for="card in cards"
          :key="card.key"
          class="rounded-cx border border-cx-border bg-cx-surface p-4 shadow-cx"
          :data-testid="`usage-card-${card.key}`"
        >
          <dt class="text-xs font-semibold text-cx-ink-3">{{ card.label }}</dt>
          <dd class="mt-1.5 text-2xl font-semibold tracking-tight text-cx-ink">
            {{ card.value }}
          </dd>
          <dd class="mt-1 text-xs text-cx-ink-2">{{ card.note }}</dd>
        </div>
      </dl>

      <p
        v-if="addedSources.length"
        class="text-sm text-cx-ink-2"
        data-testid="usage-added-sources"
      >
        Added in this range:
        <span v-for="(source, index) in addedSources" :key="source.key">
          <span class="font-semibold text-cx-ink">{{
            formatTokens(source.value)
          }}</span>
          {{ source.label.toLowerCase()
          }}<span v-if="index < addedSources.length - 1">, </span>
        </span>
      </p>

      <div
        class="rounded-cx border border-cx-border bg-cx-surface shadow-cx"
        data-testid="usage-breakdown"
      >
        <header
          class="flex flex-wrap items-baseline justify-between gap-2 border-b border-cx-border-soft px-4 py-3 sm:px-5"
        >
          <h4 class="text-base font-semibold text-cx-ink">
            Consumption by billing event
          </h4>
          <span class="text-xs text-cx-ink-2"
            >{{ report.from_date }} to {{ report.to_date }} ·
            {{ report.time_zone }}</span
          >
        </header>
        <div v-if="!report.breakdown.length" class="p-4 text-sm text-cx-ink-2">
          No tokens were used in this range.
        </div>
        <div v-else class="overflow-x-auto">
          <table class="w-full min-w-[40rem] text-left text-sm">
            <thead class="text-xs text-cx-ink-3">
              <tr>
                <th class="px-4 py-2 font-semibold sm:px-5">Billing event</th>
                <th class="px-3 py-2 text-right font-semibold">Quantity</th>
                <th class="px-3 py-2 text-right font-semibold">
                  Price (tokens)
                </th>
                <th class="px-3 py-2 text-right font-semibold">Tokens</th>
                <th class="px-4 py-2 font-semibold sm:px-5">Share</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-cx-border-soft">
              <tr v-for="item in report.breakdown" :key="item.billing_event">
                <td class="px-4 py-2.5 sm:px-5">
                  <span class="font-medium text-cx-ink">{{ item.label }}</span>
                  <span
                    v-if="item.category"
                    class="block text-xs text-cx-ink-2"
                    >{{ item.category }}</span
                  >
                </td>
                <td class="px-3 py-2.5 text-right tabular-nums text-cx-ink">
                  {{ formatTokens(item.quantity)
                  }}<span
                    v-if="item.quantity_estimated"
                    class="ml-1 text-xs text-cx-ink-2"
                    >(estimate)</span
                  >
                </td>
                <td class="px-3 py-2.5 text-right tabular-nums text-cx-ink">
                  {{ formatTokens(item.current_price) }}
                </td>
                <td
                  class="px-3 py-2.5 text-right font-semibold tabular-nums text-cx-ink"
                >
                  {{ formatTokens(item.tokens) }}
                </td>
                <td class="px-4 py-2.5 sm:px-5">
                  <div class="flex items-center gap-2">
                    <span
                      class="h-1.5 w-24 overflow-hidden rounded-full bg-cx-well"
                      aria-hidden="true"
                    >
                      <span
                        class="block h-full rounded-full bg-cx-ink-3"
                        :style="{ width: formatShare(item.share) }"
                      />
                    </span>
                    <span class="text-xs tabular-nums text-cx-ink">{{
                      formatShare(item.share)
                    }}</span>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div
        class="rounded-cx border border-cx-border bg-cx-surface shadow-cx"
        data-testid="usage-audit"
      >
        <header class="border-b border-cx-border-soft px-4 py-3 sm:px-5">
          <h4 class="text-base font-semibold text-cx-ink">Price check</h4>
          <p class="mt-1 text-sm text-cx-ink-2">
            Each billing event is checked: tokens charged = quantity × unit
            price, and the unit price against the current price list.
          </p>
          <p
            v-if="!detail.available"
            class="mt-2 text-sm text-cx-ink-2"
            data-testid="usage-detail-note"
          >
            Event-level detail is kept for the last
            {{ detail.window_days || 30 }} days. Choose a more recent range to
            check individual events.
          </p>
          <p
            v-else-if="!detail.complete"
            class="mt-2 text-sm text-cx-ink-2"
            data-testid="usage-detail-note"
          >
            Event-level detail covers {{ detail.from }} onwards<template
              v-if="detail.truncated"
            >
              (first {{ formatTokens(detail.max_events) }} events)</template
            >. Totals above cover the full range.
          </p>
          <div v-if="checks.length" class="mt-3 flex flex-wrap gap-2">
            <span
              v-for="item in checks"
              :key="item.key"
              class="rounded-full border px-2.5 py-1 text-xs font-semibold"
              :class="TONE[item.tone]"
              :data-testid="`usage-check-${item.key}`"
            >
              {{ formatTokens(item.count) }} · {{ item.label }}
            </span>
          </div>
        </header>
        <template v-if="detail.available && report.events.length">
          <div
            class="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 sm:px-5"
          >
            <label class="inline-flex items-center gap-2 text-sm text-cx-ink-2">
              <input
                v-model="onlyFlagged"
                type="checkbox"
                class="rounded border-cx-border text-cx-brand focus:ring-cx-brand"
                data-testid="usage-only-flagged"
              />
              Only events that need a look ({{ flaggedCount }})
            </label>
            <span class="text-xs text-cx-ink-2"
              >{{ formatTokens(events.length) }} events</span
            >
          </div>
          <div class="overflow-x-auto">
            <table class="w-full min-w-[44rem] text-left text-sm">
              <thead class="text-xs text-cx-ink-3">
                <tr>
                  <th class="px-4 py-2 font-semibold sm:px-5">Time</th>
                  <th class="px-3 py-2 font-semibold">Billing event</th>
                  <th class="px-3 py-2 text-right font-semibold">Qty</th>
                  <th class="px-3 py-2 text-right font-semibold">Unit price</th>
                  <th class="px-3 py-2 text-right font-semibold">Charged</th>
                  <th class="px-4 py-2 font-semibold sm:px-5">Check</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-cx-border-soft">
                <tr
                  v-for="row in visibleEvents"
                  :key="row.event_id"
                  data-testid="usage-event-row"
                >
                  <td
                    class="whitespace-nowrap px-4 py-2 tabular-nums text-cx-ink sm:px-5"
                  >
                    {{ row.time }}
                    <span class="block font-mono text-xs text-cx-ink-2">{{
                      row.event_id
                    }}</span>
                  </td>
                  <td class="px-3 py-2 text-cx-ink">{{ row.label }}</td>
                  <td class="px-3 py-2 text-right tabular-nums text-cx-ink">
                    {{ formatTokens(row.quantity) }}
                  </td>
                  <td class="px-3 py-2 text-right tabular-nums text-cx-ink">
                    {{ formatTokens(row.unit_tokens) }}
                    <span
                      v-if="row.check === 'price_differs'"
                      class="block text-xs text-cx-warning-ink"
                      >list: {{ formatTokens(row.current_price) }}</span
                    >
                  </td>
                  <td
                    class="px-3 py-2 text-right font-semibold tabular-nums text-cx-ink"
                  >
                    {{ formatTokens(row.tokens) }}
                  </td>
                  <td class="px-4 py-2 sm:px-5">
                    <span
                      class="inline-block rounded-full border px-2 py-0.5 text-xs font-semibold"
                      :class="TONE[checkTone(row.check)]"
                      >{{ checkLabel(row.check) }}</span
                    >
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            v-if="events.length > visibleEvents.length"
            class="border-t border-cx-border-soft px-4 py-3 sm:px-5"
          >
            <button
              type="button"
              class="text-xs font-semibold text-cx-brand hover:underline"
              data-testid="usage-more-events"
              @click="eventLimit += EVENT_PAGE"
            >
              Show
              {{ Math.min(EVENT_PAGE, events.length - visibleEvents.length) }}
              more of {{ formatTokens(events.length - visibleEvents.length) }}
            </button>
          </div>
        </template>
        <p
          v-else-if="detail.available"
          class="px-4 py-3 text-sm text-cx-ink-2 sm:px-5"
        >
          No billing events in the detail window.
        </p>
      </div>

      <div
        v-if="report.daily.length"
        class="rounded-cx border border-cx-border bg-cx-surface shadow-cx"
        data-testid="usage-daily"
      >
        <header class="border-b border-cx-border-soft px-4 py-3 sm:px-5">
          <h4 class="text-base font-semibold text-cx-ink">Daily consumption</h4>
        </header>
        <ul class="divide-y divide-cx-border-soft">
          <li
            v-for="day in report.daily"
            :key="day.date"
            class="flex items-center justify-between gap-3 px-4 py-2 text-sm sm:px-5"
          >
            <span class="tabular-nums text-cx-ink">{{ day.date }}</span>
            <span class="font-semibold tabular-nums text-cx-ink"
              >{{ formatTokens(day.tokens) }} tokens</span
            >
          </li>
        </ul>
      </div>
      <p class="text-xs text-cx-ink-2">
        Patient registrations count the registrations charged in your HMIS;
        compare them with your HMIS patient register. Generated
        {{ report.generated_at }}.
      </p>
    </template>
  </section>
</template>
