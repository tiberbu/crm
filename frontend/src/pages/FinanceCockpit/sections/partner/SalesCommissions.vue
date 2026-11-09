<template>
  <div class="space-y-3">
    <!-- LIST -->
    <template v-if="mode === 'list'">
      <div class="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-200">
        Confirmed commissions are not marked Paid here. Configure the payroll component and period before recording disbursements.
      </div>
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="flex flex-wrap items-center gap-2">
          <label class="text-xs text-gray-500 dark:text-gray-400"
            >Status:</label
          >
          <select
            v-model="statusFilter"
            class="text-xs border border-gray-300 dark:border-gray-600 rounded px-2 py-1 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300"
            @change="refetchFirstPage"
          >
            <option value="">All</option>
            <option value="Reported">Reported</option>
            <option value="Confirmed">Confirmed</option>
            <option value="Rejected">Rejected</option>
            <option value="Paid">Paid</option>
          </select>
          <label class="text-xs text-gray-500 dark:text-gray-400">Invoice
            <input v-model.trim="invoiceFilter" class="ml-1 min-h-8 w-40 rounded border border-gray-300 bg-white px-2 text-xs dark:border-gray-600 dark:bg-gray-800" type="search" placeholder="Invoice number" @input="refetchFirstPage" />
          </label>
        </div>
        <Button
          variant="solid"
          theme="blue"
          :disabled="!canCreate"
          :title="!canCreate ? 'You do not have permission to create' : ''"
          @click="canCreate && goNew()"
        >
          <template #prefix><FcIcon name="plus" :size="15" /></template>
          New
        </Button>
      </div>

      <FinanceTable
        :columns="columns"
        :rows="commissions"
        :loading="loading"
        :error="error"
        empty-label="No commission records found."
        :page="page"
        :page-size="20"
        @update:page="
          (p) => {
            page = p
            refetch()
          }
        "
        @row-click="goView"
        @retry="refetch"
      >
        <template #expanded-row="{ row }">
          <div class="grid grid-cols-2 gap-3 p-4 text-xs sm:grid-cols-4">
            <div><span class="text-ink-gray-5">Source invoice</span><div class="mt-1 font-medium">{{ row.source_invoice || 'Unavailable' }}</div></div>
            <div><span class="text-ink-gray-5">Payment</span><div class="mt-1 font-medium">{{ row.payment_reference || 'Unavailable' }}</div></div>
            <div><span class="text-ink-gray-5">Calculation basis</span><div class="mt-1 font-medium">{{ formatCurrency(row.calculation_basis, row.currency) }}</div></div>
            <div><span class="text-ink-gray-5">Rate used</span><div class="mt-1 font-medium">{{ row.commission_pct }}%</div></div>
          </div>
        </template>
        <template #actions="{ row }">
          <div class="flex gap-1.5 flex-wrap">
            <template v-if="canConfirmReject">
              <button
                v-if="row.status === 'Reported'"
                class="text-xs px-2.5 py-1 rounded bg-blue-600 text-white hover:bg-blue-700 transition-colors whitespace-nowrap"
                :disabled="actionPending === row.name"
                @click.stop="confirmCommission(row.name)"
              >
                Confirm
              </button>
              <button
                v-if="row.status === 'Reported'"
                class="text-xs px-2.5 py-1 rounded border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors whitespace-nowrap"
                :disabled="actionPending === row.name"
                @click.stop="rejectCommission(row.name)"
              >
                Reject
              </button>
            </template>
          </div>
        </template>
      </FinanceTable>
    </template>

    <!-- VIEW -->
    <FinanceDetail
      v-else-if="mode === 'view'"
      doctype="CRM Sales Commission"
      :name="activeName"
      @edit="goEdit"
      @deleted="onMutated"
      @close="goList"
    />

    <!-- NEW / EDIT -->
    <FinanceForm
      v-else-if="mode === 'new' || mode === 'edit'"
      doctype="CRM Sales Commission"
      :name="mode === 'edit' ? activeName : null"
      @saved="onSaved"
      @close="goBackFromForm"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { createResource, Button } from 'frappe-ui'
import FinanceTable from '../../components/FinanceTable.vue'
import FinanceForm from '../../components/crud/FinanceForm.vue'
import FinanceDetail from '../../components/crud/FinanceDetail.vue'
import FcIcon from '../../components/crud/FcIcon.vue'
import { useCompanyContext } from '../../composables/useCompanyContext.js'
import { useBoot } from '../../composables/useBoot.js'
import { useCurrency } from '../../composables/useCurrency.js'

const { company } = useCompanyContext()
const { getRoles, isAdministrator } = useBoot()
const page = ref(0)
const statusFilter = ref('')
const invoiceFilter = ref('')
const actionPending = ref(null)

const mode = ref('list')
const activeName = ref(null)

// Gate arrays mirror the Accounts-only backend exactly.
const userRoles = getRoles()
const admin = isAdministrator()
const canConfirmReject =
  admin ||
  userRoles.some((r) =>
    [
      'Accounts User',
      'Accounts Manager',
    ].includes(r),
  )
const canCreate =
  admin ||
  userRoles.includes('Accounts Manager')

const columns = [
  { key: 'name', label: 'Commission' },
  { key: 'network_label', label: 'Network' },
  { key: 'sales_person', label: 'Sales Person' },
  {
    key: 'employee_name',
    label: 'Payroll Employee',
  },
  { key: 'customer', label: 'Customer' },
  { key: 'source_invoice', label: 'Invoice' },
  { key: 'commission_pct', label: 'Commission %', align: 'right' },
  { key: 'calculation_basis', label: 'Basis', type: 'currency', align: 'right' },
  {
    key: 'commission_amount',
    label: 'Amount',
    type: 'currency',
    align: 'right',
  },
  { key: 'finance_status', label: 'Status' },
]

const resource = createResource({
  url: 'crm.finance.api.get_sales_commissions',
  makeParams() {
    const filters = []
    if (statusFilter.value) filters.push(['status', '=', statusFilter.value])
    if (invoiceFilter.value) filters.push(['source_invoice', 'like', `%${invoiceFilter.value}%`])
    return {
      company: company.value,
      filters: JSON.stringify(filters),
      page: page.value,
      page_size: 20,
    }
  },
  auto: true,
})

const loading = computed(() => resource.loading)
const error = computed(() => resource.error)
const commissions = computed(() => resource.data || [])
const { formatCurrency } = useCurrency()

function refetch() {
  resource.fetch()
}
function refetchFirstPage() {
  page.value = 0
  refetch()
}
watch(company, () => {
  page.value = 0
  resource.fetch()
})

/* ---- Mode navigation ---- */
function goList() {
  mode.value = 'list'
  activeName.value = null
}
function goView(row) {
  activeName.value = row.name
  mode.value = 'view'
}
function goNew() {
  activeName.value = null
  mode.value = 'new'
}
function goEdit() {
  mode.value = 'edit'
}
function goBackFromForm() {
  if (activeName.value) mode.value = 'view'
  else goList()
}
function onSaved(doc) {
  activeName.value = doc?.name || activeName.value
  refetch()
  mode.value = activeName.value ? 'view' : 'list'
}
function onMutated() {
  refetch()
  goList()
}

/* ---- Workflow actions ---- */
const confirmRes = createResource({ url: 'crm.finance.api.confirm_commission' })
const rejectRes = createResource({ url: 'crm.finance.api.reject_commission' })

async function confirmCommission(name) {
  actionPending.value = name
  try {
    await confirmRes.submit({ name, company: company.value })
    resource.fetch()
  } finally {
    actionPending.value = null
  }
}
async function rejectCommission(name) {
  actionPending.value = name
  try {
    await rejectRes.submit({ name, company: company.value })
    resource.fetch()
  } finally {
    actionPending.value = null
  }
}
</script>
