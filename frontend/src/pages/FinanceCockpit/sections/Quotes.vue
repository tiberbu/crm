<template>
  <CrudSection
    ref="sectionRef"
    doctype="Quotation"
    title="Quotes"
    list-resource-url="crm.finance.api.get_quotations"
    :list-params="listParams"
    :columns="columns"
    empty-label="No quotations found."
    :read-only="true"
    :create-roles="[]"
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
        <option value="Open">Open</option>
        <option value="Replied">Replied</option>
        <option value="Partially Ordered">Partially Ordered</option>
        <option value="Ordered">Ordered</option>
        <option value="Lost">Lost</option>
        <option value="Expired">Expired</option>
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
        Sales-owned · read only for Finance
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
  { key: 'name', label: 'Quote' },
  { key: 'party_name', label: 'Party' },
  { key: 'transaction_date', label: 'Date', type: 'date' },
  { key: 'valid_till', label: 'Valid', type: 'date' },
  { key: 'modified', label: 'Last modified', type: 'datetime' },
  { key: 'owner', label: 'Created by', type: 'owner' },
  { key: 'grand_total', label: 'Total', type: 'currency', align: 'right' },
  { key: 'status', label: 'Status', type: 'status' },
]

// Default ("Active") = quotes still in play. A submitted Quotation's status is
// "Open" (submitted quotations use the native "Open" status), so the prior ['Draft','Submitted']
// default silently hid every submitted quote. These are the real in-play values.
const ACTIVE_STATUSES = ['Draft', 'Open', 'Replied', 'Partially Ordered']
const hasFilters = computed(() => !!statusFilter.value)

function listParams() {
  const filters = []
  if (statusFilter.value === 'all') {
    // no filter
  } else if (statusFilter.value) {
    filters.push(['status', '=', statusFilter.value])
  } else {
    filters.push(['status', 'in', ACTIVE_STATUSES])
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
