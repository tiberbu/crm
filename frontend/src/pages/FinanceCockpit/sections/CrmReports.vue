<template>
  <div class="crm-reports space-y-5">
    <!-- Report selector tabs -->
    <div class="flex flex-wrap items-center justify-between gap-3">
      <FinanceSectionTabs
        :model-value="active"
        :tabs="REPORT_DEFS"
        aria-label="Finance reports"
        @update:model-value="selectReport"
      />
      <div
        v-if="customReportName"
        class="flex items-center gap-2 rounded-lg border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-xs text-ink-gray-7"
      >
        <span class="font-medium">{{ customReportName }}</span>
        <span v-if="filterSummary" class="text-ink-gray-5">· {{ filterSummary }}</span>
        <button
          type="button"
          class="ml-1 font-medium text-ink-blue-6 hover:underline"
          @click="clearCustomReport"
        >
          Reset
        </button>
      </div>
    </div>

    <!-- Report body -->
    <div v-if="loading" class="space-y-2">
      <div
        v-for="n in 8"
        :key="n"
        class="h-10 rounded-lg bg-surface-gray-2 animate-pulse"
      />
    </div>

    <FinanceErrorState v-else-if="error" :error="resource.error" @retry="resource.fetch()" />

    <div
      v-else-if="columns.length && rows.length"
      class="rounded-xl border border-outline-gray-1 overflow-auto"
    >
      <table class="w-full text-sm">
        <thead>
          <tr class="bg-surface-gray-2 border-b border-outline-gray-1">
            <th
              v-for="col in columns"
              :key="col.fieldname || col.label"
              class="px-4 py-2.5 text-left text-xs font-semibold text-ink-gray-5 uppercase tracking-wide whitespace-nowrap"
              :class="isNumeric(col) ? 'text-right' : ''"
            >
              {{ col.label }}
            </th>
          </tr>
        </thead>
        <tbody class="divide-y divide-outline-gray-1">
          <tr
            v-for="(row, i) in rows"
            :key="i"
            class="hover:bg-surface-gray-1 transition-colors"
            :class="row.bold ? 'font-semibold bg-surface-gray-1' : ''"
          >
            <td
              v-for="col in columns"
              :key="col.fieldname || col.label"
              class="px-4 py-2.5 text-ink-gray-7 whitespace-nowrap"
              :class="isNumeric(col) ? 'text-right tabular-nums' : ''"
            >
              {{ cellValue(row, col) }}
            </td>
          </tr>
        </tbody>
      </table>
      <div
        class="px-4 py-2 text-xs text-ink-gray-4 border-t border-outline-gray-1"
      >
        {{ rows.length }} rows · {{ activeReportLabel }} · {{ company }}
      </div>
    </div>

    <div v-else class="rounded-xl border border-dashed border-outline-gray-2 bg-surface-white px-5 py-12 text-center" role="status">
      <span class="mx-auto flex size-10 items-center justify-center rounded-xl bg-surface-gray-1 text-ink-gray-5"><span class="lucide-chart-no-axes-combined size-5" aria-hidden="true" /></span>
      <p class="mt-3 text-sm font-medium text-ink-gray-7">No report data for this Company and period.</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { createResource } from 'frappe-ui'
import { useCompanyContext } from '../composables/useCompanyContext.js'
import { useFinanceNavigation } from '../composables/useFinanceNavigation.js'
import FinanceSectionTabs from '../components/FinanceSectionTabs.vue'
import FinanceErrorState from '../components/FinanceErrorState.vue'

const { company } = useCompanyContext()
const { navState, navigateTo } = useFinanceNavigation()

const TODAY = () => new Date().toISOString().slice(0, 10)

const REPORT_DEFS = [
  {
    key: 'ar_aging',
    label: 'AR Aging',
    report_name: 'Accounts Receivable',
    filters: () => ({
      company: company.value,
      report_date: TODAY(),
    }),
  },
  {
    key: 'ap_aging',
    label: 'AP Aging',
    report_name: 'Accounts Payable',
    filters: () => ({
      company: company.value,
      report_date: TODAY(),
    }),
  },
  {
    key: 'revenue',
    label: 'Revenue by Customer',
    report_name: 'Sales Invoice Trends',
    filters: () => ({
      company: company.value,
      period: 'Monthly',
      based_on: 'Customer',
    }),
  },
  {
    key: 'collection',
    label: 'Collection Rate',
    report_name: 'Sales Payment Summary',
    filters: () => ({ company: company.value }),
  },
]

const active = ref('ar_aging')
const customReportName = computed(() => navState.value?.report || '')
const customFilters = computed(() => {
  const params = { ...(navState.value?.params || {}) }
  delete params.report
  delete params.tab
  delete params.doctype
  delete params.name
  delete params.mode
  return params
})

const filterSummary = computed(() =>
  Object.entries(customFilters.value)
    .filter(([k, v]) => k !== 'company' && v)
    .map(([k, v]) => `${k}: ${v}`)
    .join(', '),
)

const currentDef = computed(() =>
  REPORT_DEFS.find((r) => r.key === active.value) || REPORT_DEFS[0],
)

const activeReportLabel = computed(
  () => customReportName.value || currentDef.value?.label || 'Report',
)

const resource = createResource({
  url: 'frappe.desk.query_report.run',
  makeParams() {
    if (customReportName.value) {
      return {
        report_name: customReportName.value,
        filters: {
          company: company.value,
          report_date: TODAY(),
          ...customFilters.value,
        },
        ignore_prepared_report: 1,
      }
    }
    const def = currentDef.value
    return {
      report_name: def.report_name,
      filters: def.filters(),
      ignore_prepared_report: 1,
    }
  },
  auto: true,
})

const loading = computed(() => resource.loading)
const error = computed(() =>
  resource.error ? 'The report could not be loaded. Check your connection and try again.' : null,
)

const columns = computed(() => resource.data?.columns || [])
const rows = computed(() => {
  const raw = resource.data?.result || []
  return raw.filter((r) =>
    Array.isArray(r) ? r.some(Boolean) : Object.values(r).some(Boolean),
  )
})

function selectReport(key) {
  active.value = key
  if (customReportName.value) {
    navigateTo('reports')
  } else {
    resource.fetch()
  }
}

function clearCustomReport() {
  navigateTo('reports')
}

watch(
  () => [company.value, customReportName.value, JSON.stringify(customFilters.value)],
  () => resource.fetch(),
)

function isNumeric(col) {
  return ['Currency', 'Float', 'Int', 'Percent'].includes(col.fieldtype)
}

function cellValue(row, col) {
  const v = Array.isArray(row)
    ? row[columns.value.indexOf(col)]
    : row[col.fieldname || col.label]
  if (v == null || v === '') return '—'
  return v
}
</script>
