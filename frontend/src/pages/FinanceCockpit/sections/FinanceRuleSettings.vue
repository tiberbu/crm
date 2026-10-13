<template>
  <section class="space-y-6" aria-labelledby="finance-rule-settings-title">
    <header>
      <h3 id="finance-rule-settings-title" class="text-base font-semibold text-ink-gray-9">Commission and rebate rates</h3>
      <p class="mt-1 max-w-3xl text-sm text-ink-gray-6">
        Set the percentage applied to each eligible invoice payment. Rates are saved with each result so earlier payments keep their original calculation.
      </p>
    </header>

    <div v-if="loadError" class="rounded-lg border border-outline-red-2 bg-surface-red-1 p-3 text-sm text-ink-red-6" role="alert">{{ loadError }}</div>
    <div v-if="notice" class="rounded-lg border border-outline-green-2 bg-surface-green-1 p-3 text-sm text-ink-green-6" role="status">{{ notice }}</div>

    <section class="fc-card-frame overflow-hidden" aria-labelledby="rebate-rates-title">
      <div class="border-b border-outline-gray-1 px-4 py-3">
        <h4 id="rebate-rates-title" class="text-sm font-semibold text-ink-gray-9">Partner rebates</h4>
        <p class="mt-1 text-xs text-ink-gray-5">Facility Supplier is used when selected in Opt-In. Otherwise, the Network Supplier below is used.</p>
      </div>
      <div v-if="loading" class="p-4 text-sm text-ink-gray-5" role="status">Loading Network settings…</div>
      <div v-else-if="!networks.length" class="p-4 text-sm text-ink-gray-5">No Opt-In Networks are available.</div>
      <div v-else class="divide-y divide-outline-gray-1">
        <article v-for="network in networks" :key="network.name" class="grid gap-3 p-4 md:grid-cols-[minmax(10rem,1fr)_8rem_minmax(12rem,1fr)_auto] md:items-end">
          <div class="min-w-0">
            <div class="text-sm font-medium text-ink-gray-9">{{ network.display_name || network.name }}</div>
            <div class="mt-0.5 text-xs text-ink-gray-5">Partner ID {{ network.partner_id || '—' }}</div>
          </div>
          <label class="block text-xs font-medium text-ink-gray-6">
            Rebate rate (%)
            <input v-model.number="network.rebate_pct" type="number" min="0" max="100" step="0.01" inputmode="decimal" class="mt-1 min-h-10 w-full rounded-md border border-outline-gray-2 bg-surface-white px-3 text-sm text-ink-gray-9" :aria-label="`Rebate percentage for ${network.display_name || network.name}`" />
          </label>
          <label class="block text-xs font-medium text-ink-gray-6">
            Network Supplier (fallback)
            <select v-model="network.finance_supplier" class="mt-1 min-h-10 w-full rounded-md border border-outline-gray-2 bg-surface-white px-3 text-sm text-ink-gray-9" :aria-label="`Fallback Supplier for ${network.display_name || network.name}`">
              <option value="">Select a Supplier</option>
              <option v-for="supplier in suppliers" :key="supplier.name" :value="supplier.name">{{ supplier.supplier_name || supplier.name }}</option>
            </select>
          </label>
          <button type="button" class="min-h-10 rounded-md bg-ink-blue-6 px-4 text-sm font-medium text-white disabled:opacity-50" :disabled="saving === network.name" @click="saveRebate(network)">{{ saving === network.name ? 'Saving…' : 'Save' }}</button>
        </article>
      </div>
    </section>

    <section class="fc-card-frame overflow-hidden" aria-labelledby="commission-rates-title">
      <div class="border-b border-outline-gray-1 px-4 py-3">
        <h4 id="commission-rates-title" class="text-sm font-semibold text-ink-gray-9">Employee commissions</h4>
        <p class="mt-1 text-xs text-ink-gray-5">The commission is assigned to the active Employee linked to the Deal User and is based on each received invoice allocation.</p>
      </div>
      <form class="grid gap-3 border-b border-outline-gray-1 p-4 md:grid-cols-[minmax(12rem,1fr)_8rem_auto_auto] md:items-end" @submit.prevent="saveCommission">
        <label class="block text-xs font-medium text-ink-gray-6">Employee
          <select v-model="commissionForm.employee" required class="mt-1 min-h-10 w-full rounded-md border border-outline-gray-2 bg-surface-white px-3 text-sm text-ink-gray-9">
            <option value="">Select an Employee</option>
            <option v-for="employee in employees" :key="employee.name" :value="employee.name">{{ employee.employee_name || employee.name }}</option>
          </select>
        </label>
        <label class="block text-xs font-medium text-ink-gray-6">Commission rate (%)
          <input v-model.number="commissionForm.commission_pct" type="number" min="0" max="100" step="0.01" inputmode="decimal" required class="mt-1 min-h-10 w-full rounded-md border border-outline-gray-2 bg-surface-white px-3 text-sm text-ink-gray-9" />
        </label>
        <label class="flex min-h-10 items-center gap-2 text-sm text-ink-gray-7"><input v-model="commissionForm.enabled" type="checkbox" /> Enabled</label>
        <button type="submit" class="min-h-10 rounded-md bg-ink-blue-6 px-4 text-sm font-medium text-white disabled:opacity-50" :disabled="!commissionForm.employee || saving === 'commission'">{{ saving === 'commission' ? 'Saving…' : 'Save rate' }}</button>
      </form>
      <FinanceTable
        :columns="commissionColumns"
        :rows="commissionRows"
        :loading="loading"
        empty-label="No Employee commission rates configured."
      >
        <template #actions="{ row }">
          <button type="button" class="text-xs font-medium text-ink-blue-6 underline underline-offset-2" @click="editCommission(row)">Edit rate</button>
        </template>
      </FinanceTable>
    </section>

    <section class="fc-card-frame overflow-hidden" aria-labelledby="link-review-title">
      <div class="border-b border-outline-gray-1 px-4 py-3">
        <h4 id="link-review-title" class="text-sm font-semibold text-ink-gray-9">Record links for review</h4>
        <p class="mt-1 text-xs text-ink-gray-5">These records have conflicting or unresolved Network references. They are not changed automatically.</p>
      </div>
      <p v-if="!conflictRows.length && !loading" class="p-4 text-sm text-ink-gray-5" role="status">No conflicting Network references were found.</p>
      <FinanceTable v-else :columns="conflictColumns" :rows="conflictRows" :loading="loading" empty-label="No conflicting Network references were found." />
    </section>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { createResource } from 'frappe-ui'
import FinanceTable from '../components/FinanceTable.vue'

const networks = ref([])
const employees = ref([])
const suppliers = ref([])
const commissionRows = ref([])
const conflictRows = ref([])
const loading = ref(true)
const saving = ref('')
const loadError = ref('')
const notice = ref('')
const commissionForm = reactive({ employee: '', commission_pct: null, enabled: true })

const optionsResource = createResource({ url: 'crm.finance.api.get_finance_rule_options' })
const networkResource = createResource({ url: 'crm.finance.api.get_network_rebate_settings' })
const commissionsResource = createResource({ url: 'crm.finance.api.get_employee_commission_rates' })
const conflictsResource = createResource({ url: 'crm.finance.api.get_optin_network_conflicts' })
const saveRebateResource = createResource({ url: 'crm.finance.api.save_network_rebate_settings' })
const saveCommissionResource = createResource({ url: 'crm.finance.api.save_employee_commission_rate' })

const commissionColumns = [
  { key: 'employee_label', label: 'Employee' },
  { key: 'commission_pct', label: 'Rate (%)', align: 'right' },
  { key: 'enabled_label', label: 'Status' },
]
const conflictColumns = [
  { key: 'doctype', label: 'Record type' },
  { key: 'name', label: 'Record' },
  { key: 'source_summary', label: 'References' },
]

onMounted(load)

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const [options, rebateRows, rates, conflicts] = await Promise.all([
      optionsResource.fetch(),
      networkResource.fetch(),
      commissionsResource.fetch(),
      conflictsResource.fetch(),
    ])
    employees.value = options?.employees || []
    suppliers.value = options?.suppliers || []
    networks.value = (rebateRows || []).map((row) => ({ rebate_pct: 0, finance_supplier: '', ...row }))
    commissionRows.value = (rates || []).map((row) => ({
      ...row,
      employee_label: employees.value.find((employee) => employee.name === row.employee)?.employee_name || row.employee,
      enabled_label: row.enabled ? 'Enabled' : 'Disabled',
    }))
    conflictRows.value = (conflicts || []).map((row) => ({
      ...row,
      source_summary: Object.entries(row.sources || {}).map(([key, value]) => `${key}: ${value}`).join(' · '),
    }))
  } catch (error) {
    loadError.value = error?.messages?.[0] || 'Finance settings could not be loaded. Try again.'
  } finally {
    loading.value = false
  }
}

async function saveRebate(network) {
  saving.value = network.name
  notice.value = ''
  loadError.value = ''
  try {
    await saveRebateResource.fetch({
      network: network.name,
      rebate_pct: network.rebate_pct,
      supplier: network.finance_supplier || '',
    })
    notice.value = `Rebate settings saved for ${network.display_name || network.name}.`
    await load()
  } catch (error) {
    loadError.value = error?.messages?.[0] || 'Rebate settings could not be saved.'
  } finally {
    saving.value = ''
  }
}

function editCommission(row) {
  commissionForm.employee = row.employee
  commissionForm.commission_pct = Number(row.commission_pct)
  commissionForm.enabled = Boolean(row.enabled)
}

async function saveCommission() {
  saving.value = 'commission'
  notice.value = ''
  loadError.value = ''
  try {
    await saveCommissionResource.fetch({
      employee: commissionForm.employee,
      commission_pct: commissionForm.commission_pct,
      enabled: commissionForm.enabled ? 1 : 0,
    })
    notice.value = 'Employee commission rate saved.'
    commissionForm.employee = ''
    commissionForm.commission_pct = null
    commissionForm.enabled = true
    await load()
  } catch (error) {
    loadError.value = error?.messages?.[0] || 'Commission rate could not be saved.'
  } finally {
    saving.value = ''
  }
}
</script>
