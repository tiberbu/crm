<template>
  <div class="h-full overflow-auto bg-surface-gray-1">
    <main class="mx-auto max-w-[1600px] px-5 py-6 sm:px-8 lg:px-10">
      <header
        class="flex flex-col gap-5 border-b border-outline-gray-2 pb-6 lg:flex-row lg:items-end lg:justify-between"
      >
        <div>
          <div
            class="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-[0.16em] text-ink-gray-5"
          >
            <span class="size-2 rounded-full bg-red-600" />
            {{ __('Sales operations') }}
          </div>
          <h1
            class="text-2xl font-semibold tracking-tight text-ink-gray-9 sm:text-3xl"
          >
            {{ __('Opt-In Dashboard') }}
          </h1>
          <p class="mt-1.5 text-sm text-ink-gray-5">
            {{
              __(
                'Submission health, contract progress, and annual value in one view.',
              )
            }}
          </p>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <div
            class="flex rounded-lg bg-surface-gray-2 p-1 dark:bg-surface-gray-3"
          >
            <button
              v-for="option in periods"
              :key="option.value"
              class="rounded-md px-3 py-1.5 text-xs font-medium transition-all duration-200"
              :class="
                period === option.value
                  ? 'bg-surface-white text-ink-gray-9 shadow-sm dark:bg-surface-gray-1'
                  : 'text-ink-gray-5 hover:text-ink-gray-8'
              "
              @click="period = option.value"
            >
              {{ __(option.label) }}
            </button>
          </div>
          <select
            v-model="network"
            class="h-8 rounded-lg border border-outline-gray-2 bg-surface-white px-2.5 text-xs font-medium text-ink-gray-7 outline-none transition focus:border-outline-red-4 dark:bg-surface-gray-1"
          >
            <option value="">{{ __('All networks') }}</option>
            <option
              v-for="option in networkOptions"
              :key="option"
              :value="option"
            >
              {{ option }}
            </option>
          </select>
          <Button
            variant="subtle"
            size="sm"
            :loading="dashboardResource.loading"
            @click="dashboardResource.reload()"
          >
            <template #prefix><RefreshCw class="size-3.5" /></template>
            {{ __('Refresh') }}
          </Button>
        </div>
      </header>

      <div
        v-if="dashboardResource.loading && !dashboard"
        class="grid min-h-[420px] place-items-center"
      >
        <div class="flex items-center gap-3 text-sm text-ink-gray-5">
          <span
            class="size-5 animate-spin rounded-full border-2 border-red-600 border-t-transparent"
          />
          {{ __('Loading Opt-In metrics…') }}
        </div>
      </div>

      <div
        v-else-if="dashboardResource.error"
        class="grid min-h-[420px] place-items-center text-center"
      >
        <div>
          <p class="text-sm font-medium text-ink-gray-8">
            {{ __('Could not load the Opt-In dashboard') }}
          </p>
          <Button
            class="mt-3"
            size="sm"
            variant="subtle"
            @click="dashboardResource.reload()"
            >{{ __('Try again') }}</Button
          >
        </div>
      </div>

      <template v-else>
        <section
          class="grid divide-y divide-outline-gray-2 border-b border-outline-gray-2 sm:grid-cols-2 sm:divide-x sm:divide-y-0 xl:grid-cols-4"
        >
          <div
            v-for="metric in metrics"
            :key="metric.label"
            class="group px-0 py-5 sm:px-5 xl:first:pl-0 xl:last:pr-0"
          >
            <div class="flex items-center justify-between gap-3">
              <p
                class="text-xs font-medium uppercase tracking-[0.12em] text-ink-gray-5"
              >
                {{ __(metric.label) }}
              </p>
              <component
                :is="metric.icon"
                :class="['size-4', metric.iconClass]"
              />
            </div>
            <p
              class="mt-2.5 text-3xl font-semibold tracking-tight text-ink-gray-9 transition-transform duration-200 group-hover:translate-x-0.5"
            >
              {{ metric.value }}
            </p>
            <p class="mt-1 text-xs text-ink-gray-5">{{ metric.detail }}</p>
          </div>
        </section>

        <section
          class="grid gap-5 border-b border-outline-gray-2 py-6 lg:grid-cols-[220px_minmax(0,1fr)] lg:items-center"
        >
          <div>
            <h2 class="text-base font-semibold text-ink-gray-9">
              {{ __('Conversion path') }}
            </h2>
            <p class="mt-1 text-sm text-ink-gray-5">
              {{ __('Where submitted clients are in the Opt-In process.') }}
            </p>
          </div>
          <div
            class="grid grid-cols-2 divide-x divide-y divide-outline-gray-2 border border-outline-gray-2 sm:grid-cols-4 sm:divide-y-0"
          >
            <div
              v-for="stage in dashboard.funnel"
              :key="stage.label"
              class="px-4 py-3.5 first:pl-4 sm:first:pl-5"
            >
              <p class="text-2xl font-semibold tracking-tight text-ink-gray-9">
                {{ stage.value }}
              </p>
              <p class="mt-1 text-xs text-ink-gray-5">{{ __(stage.label) }}</p>
            </div>
          </div>
        </section>

        <section
          class="grid gap-8 border-b border-outline-gray-2 py-8 xl:grid-cols-[minmax(0,1.55fr)_minmax(320px,0.75fr)]"
        >
          <div>
            <div class="mb-5 flex items-start justify-between gap-4">
              <div>
                <h2 class="text-base font-semibold text-ink-gray-9">
                  {{ __('Opt-In momentum') }}
                </h2>
                <p class="mt-1 text-sm text-ink-gray-5">
                  {{
                    __(
                      'Submitted, processed, and facility-signed clients over time.',
                    )
                  }}
                </p>
              </div>
              <span class="hidden text-xs text-ink-gray-4 sm:block">{{
                periodLabel
              }}</span>
            </div>
            <G2Chart
              :options="trendChartOptions"
              :has-data="dashboard.trend.length > 0"
              :height="294"
            />
            <div
              class="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs text-ink-gray-5"
            >
              <span
                v-for="legend in trendLegend"
                :key="legend.label"
                class="flex items-center gap-2"
              >
                <span
                  class="size-2 rounded-full"
                  :style="{ backgroundColor: legend.color }"
                />
                {{ __(legend.label) }}
              </span>
            </div>
          </div>

          <div
            class="border-t border-outline-gray-2 pt-7 xl:border-l xl:border-t-0 xl:pl-8 xl:pt-0"
          >
            <div class="flex items-start justify-between gap-4">
              <div>
                <h2 class="text-base font-semibold text-ink-gray-9">
                  {{ __('Facility signing') }}
                </h2>
                <p class="mt-1 text-sm text-ink-gray-5">
                  {{
                    __('Current signatory status across generated contracts.')
                  }}
                </p>
              </div>
              <span class="text-sm font-semibold text-ink-gray-8"
                >{{ dashboard.summary.signature_rate }}%</span
              >
            </div>
            <div class="relative mt-3">
              <G2Chart
                :options="signingChartOptions"
                :has-data="signingTotal > 0"
                :height="238"
                :empty-label="__('No generated contracts in this period')"
              />
              <div
                v-if="signingTotal"
                class="pointer-events-none absolute inset-0 grid place-items-center pb-5 text-center"
              >
                <div>
                  <p
                    class="text-2xl font-semibold tracking-tight text-ink-gray-9"
                  >
                    {{ dashboard.summary.signed }}
                  </p>
                  <p
                    class="text-[11px] font-medium uppercase tracking-[0.12em] text-ink-gray-5"
                  >
                    {{ __('signed') }}
                  </p>
                </div>
              </div>
            </div>
            <div class="mt-1 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
              <div
                v-for="state in dashboard.signing_breakdown"
                :key="state.label"
                class="flex items-center justify-between gap-2"
              >
                <span class="flex items-center gap-2 text-ink-gray-5"
                  ><span
                    class="size-2 rounded-full"
                    :style="{ backgroundColor: stateColor(state.label) }"
                  />{{ __(state.label) }}</span
                >
                <span class="font-medium text-ink-gray-8">{{
                  state.value
                }}</span>
              </div>
            </div>
          </div>
        </section>

        <section
          class="grid gap-8 border-b border-outline-gray-2 py-8 xl:grid-cols-[minmax(0,1.05fr)_minmax(390px,0.95fr)]"
        >
          <div>
            <div class="mb-5">
              <h2 class="text-base font-semibold text-ink-gray-9">
                {{ __('Facility profile') }}
              </h2>
              <p class="mt-1 text-sm text-ink-gray-5">
                {{
                  __(
                    'Opted-in facilities by KEPH level, based on canonical submission data.',
                  )
                }}
              </p>
            </div>
            <G2Chart
              :options="facilityChartOptions"
              :has-data="dashboard.facility_levels.length > 0"
              :height="286"
              :empty-label="__('No processed facilities in this period')"
            />
          </div>

          <div
            class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-white dark:bg-surface-gray-1"
          >
            <div
              class="flex items-center justify-between border-b border-outline-gray-2 px-5 py-4"
            >
              <div>
                <h2 class="text-base font-semibold text-ink-gray-9">
                  {{ __('Facility-level value') }}
                </h2>
                <p class="mt-0.5 text-xs text-ink-gray-5">
                  {{ __('Annual subscription before VAT') }}
                </p>
              </div>
              <span class="text-xs font-medium text-ink-gray-5"
                >{{ dashboard.summary.facilities }} {{ __('facilities') }}</span
              >
            </div>
            <div
              v-if="dashboard.facility_levels.length"
              class="divide-y divide-outline-elevation-2"
            >
              <div
                v-for="row in dashboard.facility_levels"
                :key="row.level"
                class="grid grid-cols-[minmax(70px,0.8fr)_0.75fr_1fr] items-center gap-3 px-5 py-3 text-sm"
              >
                <span class="font-medium text-ink-gray-8">{{ row.level }}</span>
                <span class="text-right text-ink-gray-5"
                  >{{ row.facilities }} {{ __('sites') }}</span
                >
                <div class="text-right">
                  <p class="font-medium text-ink-gray-8">
                    {{ formatKes(row.annual_value) }}
                  </p>
                  <p class="mt-0.5 text-xs text-ink-gray-4">{{ row.share }}%</p>
                </div>
              </div>
            </div>
            <div
              v-else
              class="grid min-h-56 place-items-center text-sm text-ink-gray-4"
            >
              {{ __('No facility data yet') }}
            </div>
          </div>
        </section>

        <section class="border-b border-outline-gray-2 py-8">
          <div class="mb-5 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 class="text-base font-semibold text-ink-gray-9">
                {{ __('Facility contract sign-off') }}
              </h2>
              <p class="mt-1 text-sm text-ink-gray-5">
                {{
                  __(
                    'See the current facility, network, and Tiberbu approval state for each submitted facility.',
                  )
                }}
              </p>
            </div>
            <span class="text-xs text-ink-gray-4"
              >{{ dashboard.facility_progress_total }}
              {{ __('facilities') }}</span
            >
          </div>
          <div
            v-if="dashboard.facility_progress.length"
            class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-white dark:bg-surface-gray-1"
          >
            <button
              v-for="row in dashboard.facility_progress"
              :key="`${row.network}-${row.mfl_code || row.facility_name}`"
              class="grid w-full gap-3 border-b border-outline-elevation-2 px-5 py-4 text-left last:border-b-0 transition-colors hover:bg-surface-gray-1 dark:hover:bg-surface-gray-2 lg:grid-cols-[minmax(180px,1.15fr)_minmax(230px,1fr)_auto] lg:items-center"
              @click="openFacility(row)"
            >
              <div class="min-w-0">
                <p class="truncate text-sm font-medium text-ink-gray-8">
                  {{ row.facility_name }}
                </p>
                <p class="mt-0.5 truncate text-xs text-ink-gray-5">
                  {{ row.network }} · {{ row.level }}
                  <template v-if="row.mfl_code"> · {{ row.mfl_code }}</template>
                </p>
              </div>
              <div class="grid grid-cols-3 gap-2 text-xs">
                <div>
                  <p class="text-ink-gray-4">{{ __('Facility sign-off') }}</p>
                  <span :class="roleProgressClass(row.facility)">
                    {{ roleProgress(row.facility) }}
                  </span>
                </div>
                <div>
                  <p class="text-ink-gray-4">{{ __('Network sign-off') }}</p>
                  <span :class="roleProgressClass(row.network_signatories)">
                    {{ roleProgress(row.network_signatories) }}
                  </span>
                </div>
                <div>
                  <p class="text-ink-gray-4">{{ __('Tiberbu sign-off') }}</p>
                  <span :class="roleProgressClass(row.tiberbu_signatories)">
                    {{ roleProgress(row.tiberbu_signatories) }}
                  </span>
                </div>
              </div>
              <span :class="signoffPill(row)">{{ __(row.state) }}</span>
            </button>
          </div>
          <div
            v-else
            class="grid min-h-32 place-items-center rounded-xl border border-dashed border-outline-gray-2 text-sm text-ink-gray-4"
          >
            {{ __('No processed facilities in this period') }}
          </div>
        </section>

        <section
          class="grid gap-8 border-b border-outline-gray-2 py-8 xl:grid-cols-3"
        >
          <div>
            <div class="mb-4">
              <h2 class="text-base font-semibold text-ink-gray-9">
                {{ __('Stage turnaround') }}
              </h2>
              <p class="mt-1 text-sm text-ink-gray-5">
                {{ __('Median and slowest 10% of completed hand-offs.') }}
              </p>
            </div>
            <div
              class="divide-y divide-outline-elevation-2 border-y border-outline-gray-2"
            >
              <div
                v-for="stage in dashboard.tat"
                :key="stage.key"
                class="flex items-center justify-between gap-3 py-3"
              >
                <div class="min-w-0">
                  <p class="text-xs font-medium text-ink-gray-7">
                    {{ __(stage.label) }}
                  </p>
                  <p class="mt-0.5 text-xs text-ink-gray-4">
                    {{ stage.sample_size }} {{ __('completed') }}
                  </p>
                </div>
                <div class="shrink-0 text-right">
                  <p class="text-sm font-semibold text-ink-gray-8">
                    {{ formatDuration(stage.median_hours) }}
                  </p>
                  <p class="mt-0.5 text-[11px] text-ink-gray-4">
                    {{ __('P90') }} {{ formatDuration(stage.p90_hours) }}
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div>
            <div class="mb-4">
              <h2 class="text-base font-semibold text-ink-gray-9">
                {{ __('Signatory leaders') }}
              </h2>
              <p class="mt-1 text-sm text-ink-gray-5">
                {{
                  __(
                    'Network and Tiberbu signatories with the most completions.',
                  )
                }}
              </p>
            </div>
            <div
              v-if="dashboard.signatory_leaderboard.length"
              class="divide-y divide-outline-elevation-2 border-y border-outline-gray-2"
            >
              <div
                v-for="(row, index) in dashboard.signatory_leaderboard"
                :key="`${row.role}-${row.email || row.name}`"
                class="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 py-3"
              >
                <span
                  class="grid size-6 place-items-center rounded-full bg-surface-gray-2 text-xs font-semibold text-ink-gray-6 dark:bg-surface-gray-3"
                  >{{ index + 1 }}</span
                >
                <div class="min-w-0">
                  <p class="truncate text-sm font-medium text-ink-gray-8">
                    {{ row.name }}
                  </p>
                  <p class="mt-0.5 truncate text-xs text-ink-gray-5">
                    {{ __(row.role) }} · {{ row.networks.join(', ') }}
                  </p>
                </div>
                <div class="text-right">
                  <p class="text-sm font-semibold text-ink-gray-8">
                    {{ signatoryProgress(row) }}
                  </p>
                  <p class="mt-0.5 text-[11px] text-ink-gray-4">
                    {{ formatDuration(row.median_response_hours) }}
                    {{ __('median') }}
                  </p>
                </div>
              </div>
            </div>
            <div
              v-else
              class="grid min-h-40 place-items-center border-y border-outline-gray-2 text-sm text-ink-gray-4"
            >
              {{ __('No completed counterparty signatures yet') }}
            </div>
          </div>

          <div>
            <div class="mb-4">
              <h2 class="text-base font-semibold text-ink-gray-9">
                {{ __('Fastest full sign-off') }}
              </h2>
              <p class="mt-1 text-sm text-ink-gray-5">
                {{
                  __('Facilities with the shortest end-to-end execution time.')
                }}
              </p>
            </div>
            <div
              v-if="dashboard.facility_leaderboard.length"
              class="divide-y divide-outline-elevation-2 border-y border-outline-gray-2"
            >
              <button
                v-for="(row, index) in dashboard.facility_leaderboard"
                :key="`${row.network}-${row.mfl_code || row.facility_name}`"
                class="grid w-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 py-3 text-left transition-colors hover:text-ink-gray-9"
                @click="openFacility(row)"
              >
                <span
                  class="grid size-6 place-items-center rounded-full bg-emerald-50 text-xs font-semibold text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300"
                  >{{ index + 1 }}</span
                >
                <div class="min-w-0">
                  <p class="truncate text-sm font-medium text-ink-gray-8">
                    {{ row.facility_name }}
                  </p>
                  <p class="mt-0.5 truncate text-xs text-ink-gray-5">
                    {{ row.network }} · {{ row.level }}
                  </p>
                </div>
                <span
                  class="text-sm font-semibold text-emerald-700 dark:text-emerald-300"
                >
                  {{ formatDuration(row.end_to_end_hours) }}
                </span>
              </button>
            </div>
            <div
              v-else
              class="grid min-h-40 place-items-center border-y border-outline-gray-2 text-sm text-ink-gray-4"
            >
              {{ __('No fully executed facilities yet') }}
            </div>
          </div>
        </section>

        <section
          class="grid gap-8 py-8 xl:grid-cols-[minmax(0,0.82fr)_minmax(0,1.18fr)]"
        >
          <div>
            <div class="mb-4 flex items-end justify-between gap-3">
              <div>
                <h2 class="text-base font-semibold text-ink-gray-9">
                  {{ __('Network adoption') }}
                </h2>
                <p class="mt-1 text-sm text-ink-gray-5">
                  {{
                    __(
                      'Eligible facilities, Opt-Ins, and fully signed agreements.',
                    )
                  }}
                </p>
              </div>
              <span class="text-xs text-ink-gray-4"
                >{{ dashboard.networks.length }} {{ __('networks') }}</span
              >
            </div>
            <div
              v-if="dashboard.networks.length"
              class="divide-y divide-outline-elevation-2 border-y border-outline-gray-2"
            >
              <div class="px-1 py-4 sm:px-2">
                <p class="mb-2 text-xs font-medium text-ink-gray-5">
                  {{ __('Opted-in facility distribution') }}
                </p>
                <G2Chart
                  :options="networkDistributionOptions"
                  :has-data="networkDistribution.length > 0"
                  :height="networkDistributionHeight"
                  :empty-label="__('No opted-in facilities in this period')"
                />
              </div>
              <div
                v-for="row in dashboard.networks"
                :key="row.network"
                class="py-3.5"
              >
                <div class="flex items-center justify-between gap-4 text-sm">
                  <span class="font-medium text-ink-gray-8">{{
                    row.network
                  }}</span>
                  <span class="text-xs font-medium text-ink-gray-6">
                    {{ formatPercent(row.opt_in_rate) }} {{ __('opted in') }}
                  </span>
                </div>
                <div class="mt-2 flex items-center gap-3">
                  <div
                    class="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-gray-2 dark:bg-surface-gray-3"
                  >
                    <div
                      class="h-full rounded-full bg-emerald-500 transition-all duration-500"
                      :style="{ width: `${progressWidth(row.opt_in_rate)}%` }"
                    />
                  </div>
                  <span
                    class="w-10 text-right text-xs font-medium text-ink-gray-6"
                    >{{ row.opted_in_facilities }} /
                    {{ row.eligible_facilities }}</span
                  >
                </div>
                <p class="mt-1.5 text-xs text-ink-gray-5">
                  {{ row.submitted_facilities }} {{ __('submitted') }} ·
                  {{ row.fully_executed_facilities }}
                  {{ __('fully executed') }} ·
                  {{ formatKes(row.annual_value) }}
                </p>
              </div>
            </div>
            <div
              v-else
              class="grid min-h-40 place-items-center border-y border-outline-gray-2 text-sm text-ink-gray-4"
            >
              {{ __('No network activity yet') }}
            </div>
          </div>

          <div>
            <div class="mb-4 flex items-end justify-between gap-3">
              <div>
                <h2 class="text-base font-semibold text-ink-gray-9">
                  {{ __('Action queue') }}
                </h2>
                <p class="mt-1 text-sm text-ink-gray-5">
                  {{ __('Recent submissions that need a sales follow-up.') }}
                </p>
              </div>
              <span
                v-if="dashboard.attention.length"
                class="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
                >{{ dashboard.attention.length }} {{ __('open') }}</span
              >
            </div>
            <div
              v-if="dashboard.attention.length"
              class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-white dark:bg-surface-gray-1"
            >
              <button
                v-for="row in dashboard.attention"
                :key="row.submission_ref"
                class="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-4 border-b border-outline-elevation-2 px-5 py-3.5 text-left last:border-b-0 transition-colors hover:bg-surface-gray-1 dark:hover:bg-surface-gray-2"
                @click="openAttention(row)"
              >
                <div class="min-w-0">
                  <p class="truncate text-sm font-medium text-ink-gray-8">
                    {{ row.organisation || row.submission_ref }}
                  </p>
                  <p class="mt-0.5 text-xs text-ink-gray-5">
                    {{ row.submission_ref }} ·
                    {{ formatDate(row.submitted_at) }}
                  </p>
                </div>
                <div class="flex items-center gap-2">
                  <span :class="attentionPill(row.state)">{{
                    __(row.issue)
                  }}</span>
                  <ChevronRight class="size-4 text-ink-gray-4" />
                </div>
              </button>
            </div>
            <div
              v-else
              class="grid min-h-40 place-items-center rounded-xl border border-dashed border-outline-gray-2 text-center"
            >
              <div>
                <CheckCircle2 class="mx-auto size-5 text-emerald-600" />
                <p class="mt-2 text-sm font-medium text-ink-gray-7">
                  {{ __('No follow-up required') }}
                </p>
              </div>
            </div>
          </div>
        </section>
      </template>
    </main>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Button, createResource } from 'frappe-ui'
import ArrowUpRight from '~icons/lucide/arrow-up-right'
import CheckCircle2 from '~icons/lucide/circle-check-big'
import ChevronRight from '~icons/lucide/chevron-right'
import Clock3 from '~icons/lucide/clock-3'
import FileSignature from '~icons/lucide/file-signature'
import RefreshCw from '~icons/lucide/refresh-cw'
import TrendingUp from '~icons/lucide/trending-up'
import G2Chart from '@/components/OptInDashboard/G2Chart.vue'

const router = useRouter()
const period = ref('30d')
const network = ref('')
const periods = [
  { label: '7 days', value: '7d' },
  { label: '30 days', value: '30d' },
  { label: '90 days', value: '90d' },
  { label: 'All time', value: 'all' },
]
const trendLegend = [
  { label: 'Submitted', color: '#d92d20' },
  { label: 'Processed', color: '#175cd3' },
  { label: 'Facility signed', color: '#039855' },
]

const dashboardResource = createResource({
  url: 'crm.api.optin.get_optin_dashboard',
  makeParams: () => ({
    period: period.value,
    network_slug: network.value || null,
  }),
  auto: true,
})

watch([period, network], () => dashboardResource.reload())

const emptyDashboard = {
  summary: {
    submissions: 0,
    processed: 0,
    in_progress: 0,
    failed: 0,
    clients: 0,
    facilities: 0,
    annual_value: 0,
    contracts: 0,
    signed: 0,
    fully_executed: 0,
    signature_rate: 0,
  },
  funnel: [],
  trend: [],
  signing_breakdown: [],
  facility_levels: [],
  networks: [],
  attention: [],
  facility_progress: [],
  facility_progress_total: 0,
  signatory_leaderboard: [],
  tat: [],
  facility_leaderboard: [],
}
const dashboard = computed(() => dashboardResource.data ?? emptyDashboard)
const networkOptions = computed(
  () => dashboardResource.data?.network_options ?? [],
)
const signingTotal = computed(() =>
  dashboard.value.signing_breakdown.reduce((sum, row) => sum + row.value, 0),
)
const periodLabel = computed(
  () => periods.find((option) => option.value === period.value)?.label ?? '',
)

const metrics = computed(() => [
  {
    label: 'Opted-in clients',
    value: formatNumber(dashboard.value.summary.clients),
    detail: `${formatNumber(dashboard.value.summary.facilities)} facilities across processed submissions`,
    icon: TrendingUp,
    iconClass: 'text-red-600',
  },
  {
    label: 'Annual contract value',
    value: formatKes(dashboard.value.summary.annual_value),
    detail: 'Accepted quotation value, including VAT',
    icon: ArrowUpRight,
    iconClass: 'text-emerald-600',
  },
  {
    label: 'Facility signatures',
    value: `${dashboard.value.summary.signature_rate}%`,
    detail: `${dashboard.value.summary.signed} of ${dashboard.value.summary.contracts} generated contracts`,
    icon: FileSignature,
    iconClass: 'text-blue-600',
  },
  {
    label: 'Needs attention',
    value: formatNumber(dashboard.value.attention.length),
    detail: `${dashboard.value.summary.in_progress} processing · ${dashboard.value.summary.failed} failed`,
    icon: Clock3,
    iconClass: 'text-amber-600',
  },
])

const trendChartOptions = computed(() => ({
  type: 'view',
  padding: [12, 18, 30, 40],
  tooltip: { shared: true },
  scale: { y: { nice: true } },
  children: [
    lineMark('submissions', '#d92d20'),
    lineMark('processed', '#175cd3'),
    lineMark('signed', '#039855'),
  ],
}))

const signingChartOptions = computed(() => ({
  type: 'interval',
  data: dashboard.value.signing_breakdown.filter((row) => row.value > 0),
  transform: [{ type: 'stackY' }],
  coordinate: { type: 'theta', innerRadius: 0.72 },
  encode: { y: 'value', color: 'label' },
  scale: {
    color: {
      domain: [
        'Signed',
        'Awaiting signature',
        'Needs follow-up',
        'No contract',
      ],
      range: ['#039855', '#175cd3', '#d92d20', '#98a2b3'],
    },
  },
  legend: false,
  axis: false,
  style: { stroke: '#ffffff', lineWidth: 3 },
  animate: { enter: { type: 'waveIn', duration: 500 } },
}))

const facilityChartOptions = computed(() => ({
  type: 'interval',
  data: dashboard.value.facility_levels,
  padding: [12, 12, 36, 44],
  encode: { x: 'level', y: 'facilities', color: 'level' },
  scale: {
    color: {
      range: [
        '#f97066',
        '#d92d20',
        '#b42318',
        '#7a271a',
        '#175cd3',
        '#1570ef',
        '#039855',
        '#12b76a',
        '#f79009',
      ],
    },
    y: { nice: true },
  },
  legend: false,
  axis: { x: { title: false }, y: { title: false, grid: true } },
  style: { radiusTopLeft: 6, radiusTopRight: 6 },
  animate: { enter: { type: 'growInY', duration: 500 } },
  tooltip: { title: 'level', items: [{ channel: 'y', name: 'Facilities' }] },
}))

const networkDistribution = computed(() =>
  dashboard.value.networks.filter((row) => row.opted_in_facilities > 0),
)

const networkDistributionHeight = computed(() =>
  Math.max(180, Math.min(360, networkDistribution.value.length * 34 + 44)),
)

const networkDistributionOptions = computed(() => ({
  type: 'interval',
  data: networkDistribution.value,
  padding: [8, 18, 26, 92],
  coordinate: { transform: [{ type: 'transpose' }] },
  encode: { x: 'network', y: 'opted_in_facilities', color: 'network' },
  scale: {
    y: { nice: true },
    color: {
      range: [
        '#d92d20',
        '#f04438',
        '#175cd3',
        '#1570ef',
        '#039855',
        '#12b76a',
        '#f79009',
        '#7a5af8',
      ],
    },
  },
  legend: false,
  axis: { x: { title: false }, y: { title: false, grid: true } },
  style: { radiusTopRight: 5, radiusBottomRight: 5 },
  animate: { enter: { type: 'growInX', duration: 500 } },
  tooltip: {
    title: 'network',
    items: [{ channel: 'y', name: 'Opted-in facilities' }],
  },
}))

function lineMark(key, color) {
  return {
    type: 'line',
    data: dashboard.value.trend,
    encode: { x: 'label', y: key },
    style: { stroke: color, lineWidth: 2.25 },
    animate: { enter: { type: 'fadeIn', duration: 400 } },
  }
}

function stateColor(label) {
  return (
    {
      Signed: '#039855',
      'Awaiting signature': '#175cd3',
      'Needs follow-up': '#d92d20',
      'No contract': '#98a2b3',
    }[label] ?? '#98a2b3'
  )
}

function attentionPill(state) {
  const base = 'max-w-44 truncate rounded-full px-2.5 py-1 text-xs font-medium'
  if (
    state === 'Failed' ||
    state === 'Declined' ||
    state === 'Signing link expired'
  )
    return `${base} bg-red-50 text-red-700 dark:bg-red-950/30 dark:text-red-300`
  if (state === 'No contract')
    return `${base} bg-surface-gray-2 text-ink-gray-6 dark:bg-surface-gray-3 dark:text-ink-gray-4`
  return `${base} bg-amber-50 text-amber-700 dark:bg-amber-950/30 dark:text-amber-300`
}

function roleProgress(progress) {
  if (!progress?.total) return __('Not configured')
  return `${progress.signed} of ${progress.total} ${__('signed')}`
}

function signatoryProgress(row) {
  return `${row.signed} of ${row.assigned} ${__('signed')}`
}

function roleProgressClass(progress) {
  const base = 'mt-1 inline-block text-xs font-medium'
  if (!progress?.total) return `${base} text-ink-gray-4`
  if (progress.complete) return `${base} text-emerald-700 dark:text-emerald-300`
  if (progress.declined) return `${base} text-red-700 dark:text-red-300`
  return `${base} text-amber-700 dark:text-amber-300`
}

function signoffPill(row) {
  const base = 'w-fit rounded-full px-2.5 py-1 text-xs font-medium'
  if (row.fully_executed)
    return `${base} bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300`
  if (row.state?.includes('Awaiting'))
    return `${base} bg-amber-50 text-amber-700 dark:bg-amber-950/30 dark:text-amber-300`
  return `${base} bg-surface-gray-2 text-ink-gray-6 dark:bg-surface-gray-3 dark:text-ink-gray-4`
}

function progressWidth(value) {
  if (value == null) return 0
  return Math.max(0, Math.min(100, Number(value)))
}

function formatPercent(value) {
  return value == null ? __('No roster') : `${value}%`
}

function formatDuration(hours) {
  if (hours == null || Number.isNaN(Number(hours))) return '—'
  const value = Number(hours)
  if (value >= 48) return `${(value / 24).toFixed(value >= 240 ? 0 : 1)}d`
  if (value >= 1) return `${value.toFixed(value >= 10 ? 0 : 1)}h`
  return `${Math.max(1, Math.round(value * 60))}m`
}

function openAttention(row) {
  if (row.deal) {
    router.push({
      name: 'Deal',
      params: { dealId: row.deal },
      hash: '#activity',
    })
    return
  }
  router.push({ name: 'OptInSubmissions' })
}

function openFacility(row) {
  if (row.deal) {
    router.push({
      name: 'Deal',
      params: { dealId: row.deal },
      hash: '#activity',
    })
    return
  }
  router.push({ name: 'OptInSubmissions' })
}

function formatNumber(value) {
  return new Intl.NumberFormat('en-KE').format(value || 0)
}

function formatKes(value) {
  const amount = Number(value || 0)
  if (amount >= 1_000_000) return `KES ${(amount / 1_000_000).toFixed(1)}M`
  if (amount >= 1_000) return `KES ${(amount / 1_000).toFixed(0)}K`
  return `KES ${Math.round(amount).toLocaleString('en-KE')}`
}

function formatDate(value) {
  if (!value) return '—'
  return new Date(value).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
  })
}
</script>
