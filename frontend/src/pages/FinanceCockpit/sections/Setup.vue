<template>
  <div class="space-y-6">
    <header>
      <h2 class="text-lg font-semibold text-ink-gray-9">Setup</h2>
      <p class="mt-1 text-sm text-ink-gray-6">Configure finance rules and company accounting records.</p>
    </header>
    <nav class="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5" aria-label="Finance setup">
      <button v-for="item in items" :key="item.key" type="button" class="rounded-lg border px-3 py-3 text-left text-sm font-medium transition-colors" :class="selected === item.key ? 'border-ink-blue-5 bg-surface-blue-1 text-ink-blue-7' : 'border-outline-gray-2 bg-surface-white text-ink-gray-7 hover:bg-surface-gray-1'" @click="selected = item.key">
        {{ item.label }}
      </button>
    </nav>
    <FinanceRuleSettings v-if="selected === 'rules'" />
    <FinanceSetupRecords v-else :setup-key="selected" />
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import FinanceRuleSettings from './FinanceRuleSettings.vue'
import FinanceSetupRecords from './FinanceSetupRecords.vue'
import { useFinanceNavigation } from '../composables/useFinanceNavigation.js'

const items = [
  { key: 'rules', label: 'Commission and rebates' },
  { key: 'accounts', label: 'Chart of accounts' },
  { key: 'cost-centres', label: 'Cost centres' },
  { key: 'dimensions', label: 'Accounting dimensions' },
  { key: 'taxes', label: 'Tax templates' },
  { key: 'terms', label: 'Payment terms' },
  { key: 'methods', label: 'Payment methods' },
  { key: 'fiscal-year', label: 'Fiscal years' },
  { key: 'currency', label: 'Currency exchange' },
]

const { navState } = useFinanceNavigation()
const selected = ref(navState.value?.tab || 'rules')
watch(
  () => navState.value?.tab,
  (tab) => {
    if (tab && items.some((i) => i.key === tab)) selected.value = tab
  },
)
</script>
