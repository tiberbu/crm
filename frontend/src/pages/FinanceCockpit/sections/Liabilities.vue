<template>
  <div class="fc-liabilities space-y-4">
    <div class="flex items-center gap-2">
      <h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100">
        Liabilities
      </h2>
    </div>

    <FinanceSectionTabs v-model="activeTab" :tabs="TABS" aria-label="Liability views" />

    <!-- Subscriptions -->
    <div v-if="activeTab === 'subscriptions'">
      <div
        v-if="genError"
        class="mb-2 text-xs text-red-500 bg-red-50 dark:bg-red-900/20 rounded px-3 py-2"
      >
        {{ genError }}
        <button class="ml-2 underline" @click="genError = null">Dismiss</button>
      </div>
      <FinanceTable
        :columns="subCols"
        :rows="subRows"
        :loading="subLoading"
        :error="subError"
        empty-label="No subscriptions found."
        :page="subPage"
        :page-size="20"
        @update:page="
          (p) => {
            subPage = p
            subRes.fetch()
          }
        "
        @row-click="(row) => navigateTo({ doctype: 'Subscription', name: row.name, company: company })"
        @retry="subRes.fetch()"
      >
        <template #actions="{ row }">
          <button
            v-if="row.status === 'Active'"
            class="text-xs px-2.5 py-1 rounded bg-blue-600 text-white hover:bg-blue-700 transition-colors whitespace-nowrap"
            :disabled="genPending === row.name"
            @click.stop="generateInvoice(row.name)"
          >
            {{ genPending === row.name ? 'Generating...' : 'Generate Invoice' }}
          </button>
        </template>
      </FinanceTable>
    </div>

    <!-- Deferred Revenue/Expense -->
    <div v-else-if="activeTab === 'deferred'" class="py-6 text-center">
      <p class="text-sm text-gray-500 dark:text-gray-400 mb-3">
        View the Deferred Revenue and Expense report
      </p>
      <a
        :href="deferredUrl"
        class="inline-flex items-center gap-2 text-sm px-4 py-2 rounded bg-blue-600 text-white hover:bg-blue-700 transition-colors"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
          <polyline points="15 3 21 3 21 9" />
          <line x1="10" x2="21" y1="14" y2="3" />
        </svg>
        Open Deferred Revenue and Expense
      </a>
    </div>
  </div>
</template>

<script setup>
import FinanceSectionTabs from '../components/FinanceSectionTabs.vue'
import { ref, computed, watch } from 'vue'
import { createResource } from 'frappe-ui'
import FinanceTable from '../components/FinanceTable.vue'
import { useCompanyContext } from '../composables/useCompanyContext.js'
import {
  cockpitReportHref,
  useFinanceNavigation,
} from '../composables/useFinanceNavigation.js'
import { readableError } from '../composables/financeErrors.js'

const { company } = useCompanyContext()
const { navigateTo } = useFinanceNavigation()
const activeTab = ref('subscriptions')
const genPending = ref(null)

const TABS = [
  { key: 'subscriptions', label: 'Subscriptions' },
  { key: 'deferred', label: 'Deferred Revenue/Expense' },
]

const deferredUrl = computed(() =>
  cockpitReportHref('Deferred Revenue and Expense', {
    company: company.value || '',
  }),
)

const subPage = ref(0)
const subCols = [
  { key: 'name', label: 'Subscription' },
  { key: 'party', label: 'Party' },
  { key: 'status', label: 'Status', type: 'status' },
  { key: 'current_invoice_start', label: 'Period Start', type: 'date' },
  { key: 'current_invoice_end', label: 'Period End', type: 'date' },
  { key: 'days_until_due', label: 'Days Until Due', align: 'right' },
]

const subRes = createResource({
  url: 'crm.finance.api.get_subscriptions',
  makeParams() {
    return { company: company.value, page: subPage.value, page_size: 20 }
  },
  auto: true,
})
const subRows = computed(() => subRes.data || [])
const subLoading = computed(() => subRes.loading)
const subError = computed(() => subRes.error)

const genInvoiceRes = createResource({ url: 'frappe.client.run_doc_method' })
const genError = ref(null)

async function generateInvoice(name) {
  genPending.value = name
  genError.value = null
  try {
    await genInvoiceRes.submit({
      dt: 'Subscription',
      dn: name,
      method: 'generate_invoice',
    })
    subRes.fetch()
  } catch (err) {
    genError.value = readableError(err)
  } finally {
    genPending.value = null
  }
}

watch(company, () => {
  subPage.value = 0
  subRes.fetch()
})
</script>
