<template>
  <CrudSection
    ref="sectionRef"
    doctype="Sales Invoice"
    title="Invoices"
    subtitle="Prioritize overdue receivables, review the handoff, and receive payment."
    list-resource-url="crm.finance.api.get_ar_invoices"
    :list-params="listParams"
    :columns="columns"
    :create-from="createFrom"
    empty-label="No invoices found."
  >
    <template #filters>
      <label class="text-xs text-ink-gray-5">Status:</label>
      <select
        v-model="statusFilter"
        class="text-xs border border-outline-gray-2 rounded px-2 py-1 bg-surface-white text-ink-gray-7"
        @change="onFilterChange"
      >
        <option value="">All outstanding</option>
        <option value="Unpaid">Unpaid</option>
        <option value="Partly Paid">Partly Paid</option>
        <option value="Overdue">Overdue</option>
      </select>
      <label class="ml-2 text-xs text-ink-gray-5">Due:</label>
      <select
        v-model="dueFilter"
        class="text-xs border border-outline-gray-2 rounded px-2 py-1 bg-surface-white text-ink-gray-7"
        @change="onFilterChange"
      >
        <option value="all">All outstanding</option>
        <option value="overdue">Overdue</option>
        <option value="next_7">Due in the next 7 days</option>
        <option value="later">Due later</option>
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
        Sorted by due date · oldest first
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
const dueFilter = ref('all')
const sectionRef = ref(null)

const columns = [
  { key: 'name', label: 'Invoice' },
  { key: 'customer', label: 'Customer' },
  { key: 'posting_date', label: 'Posted', type: 'date' },
  { key: 'due_date', label: 'Due', type: 'due-date' },
  { key: 'days_overdue', label: 'Age', type: 'overdue' },
  { key: 'grand_total', label: 'Total', type: 'currency', align: 'right' },
  {
    key: 'outstanding_amount',
    label: 'Outstanding',
    type: 'currency',
    align: 'right',
  },
  { key: 'status', label: 'Status', type: 'status' },
  { key: 'modified', label: 'Last modified', type: 'datetime' },
  { key: 'owner', label: 'Created by', type: 'owner' },
]

const hasFilters = computed(
  () => !!statusFilter.value || dueFilter.value !== 'all',
)

function isoDate(offset = 0) {
  const value = new Date()
  value.setDate(value.getDate() + offset)
  return value.toISOString().slice(0, 10)
}

// Create-From flows for Sales Invoices:
//   1. From Sales Order — guarded native action (submitted SO → one draft invoice)
//   2. Receive Payment — seed an unsaved Payment Entry from a submitted invoice
const createFrom = [
  {
    key: 'from-order',
    label: 'Generate invoice from order',
    sourceDoctype: 'Sales Order',
    sourceLabel: 'Sales Order',
    subtitleField: 'customer',
    sourceFilters: [
      ['docstatus', '=', 1],
      ['billing_status', '=', 'Not Billed'],
    ],
    actionMethod: 'crm.finance.api.make_sales_invoice_from_order',
    actionParam: 'order_name',
    targetDoctype: 'Sales Invoice',
  },
  {
    key: 'receive-payment',
    label: 'Receive Payment',
    sourceDoctype: 'Sales Invoice',
    sourceLabel: 'Sales Invoice',
    subtitleField: 'customer',
    // Only submitted (docstatus=1) invoices with outstanding balance are valid sources.
    sourceFilters: [
      ['docstatus', '=', 1],
      ['outstanding_amount', '>', 0],
    ],
    mapMethod: 'crm.finance.api.make_payment_entry_from_invoice',
    targetDoctype: 'Payment Entry',
  },
]

function listParams() {
  const filters = []
  if (statusFilter.value) {
    filters.push(['status', '=', statusFilter.value])
  }
  if (dueFilter.value === 'overdue') {
    filters.push(['due_date', '<', isoDate()])
  } else if (dueFilter.value === 'next_7') {
    filters.push(['due_date', 'between', [isoDate(), isoDate(7)]])
  } else if (dueFilter.value === 'later') {
    filters.push(['due_date', '>', isoDate(7)])
  }
  return { company: company.value, filters: JSON.stringify(filters) }
}

function onFilterChange() {
  sectionRef.value?.resetPage()
  sectionRef.value?.refetch()
}

function clearFilters() {
  statusFilter.value = ''
  dueFilter.value = 'all'
  onFilterChange()
}
</script>
