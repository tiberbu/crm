<template>
  <CrudSection
    ref="sectionRef"
    doctype="Sales Order"
    title="Orders"
    list-resource-url="crm.finance.api.get_sales_orders"
    :list-params="listParams"
    :columns="columns"
    :create-from="createFrom"
    empty-label="No sales orders found."
    :read-only="true"
    :allow-lifecycle-actions="true"
    :create-roles="['Accounts User', 'Accounts Manager']"
  >
    <template #filters>
      <label class="text-xs text-ink-gray-5">Status:</label>
      <select
        v-model="statusFilter"
        class="text-xs border border-outline-gray-2 rounded px-2 py-1 bg-surface-white text-ink-gray-7"
        @change="onFilterChange"
      >
        <option value="">Active</option>
        <option value="all">All</option>
        <option value="Draft">Draft</option>
        <option value="To Deliver and Bill">To Deliver & Bill</option>
        <option value="To Bill">To Bill</option>
        <option value="Completed">Completed</option>
        <option value="Cancelled">Cancelled</option>
      </select>
      <button
        v-if="hasFilters"
        type="button"
        class="ml-2 text-xs font-medium text-ink-gray-6 underline underline-offset-2"
        @click="clearFilters"
      >
        Clear filters
      </button>
      <span class="ml-auto text-xs text-ink-gray-4">
        Sorted by order date · newest first
      </span>
    </template>
  </CrudSection>
</template>

<script setup>
import { ref, computed } from 'vue'
import CrudSection from '../components/crud/CrudSection.vue'
import { useCompanyContext } from '../composables/useCompanyContext.js'

const { company } = useCompanyContext()
const statusFilter = ref('')
const sectionRef = ref(null)

const columns = [
  { key: 'name', label: 'Order' },
  { key: 'customer', label: 'Customer' },
  { key: 'transaction_date', label: 'Date', type: 'timeago' },
  { key: 'delivery_date', label: 'Delivery', type: 'date' },
  { key: 'modified', label: 'Last modified', type: 'datetime' },
  { key: 'owner', label: 'Created by', type: 'owner' },
  { key: 'grand_total', label: 'Total', type: 'currency', align: 'right' },
  { key: 'status', label: 'Status', type: 'status' },
  { key: 'billing_status', label: 'Billing', type: 'status' },
]

// Create-From: submitted Quotation (docstatus=1) → Sales Order via the native mapper.
const createFrom = [
  {
    key: 'from-quotation',
    label: 'Create from Quote',
    sourceDoctype: 'Quotation',
    sourceLabel: 'Quotation',
    subtitleField: 'customer_name',
    mapMethod: 'erpnext.selling.doctype.quotation.quotation.make_sales_order',
    targetDoctype: 'Sales Order',
  },
]

const hasFilters = computed(() => !!statusFilter.value)

function listParams() {
  const filters = []
  if (statusFilter.value === 'all') {
    // no filter
  } else if (statusFilter.value) {
    filters.push(['status', '=', statusFilter.value])
  } else {
    filters.push(['status', 'in', ['Draft', 'To Deliver and Bill', 'To Bill']])
  }
  return { company: company.value, filters: JSON.stringify(filters) }
}

function onFilterChange() {
  sectionRef.value?.resetPage()
  sectionRef.value?.refetch()
}

function clearFilters() {
  statusFilter.value = ''
  onFilterChange()
}
</script>
