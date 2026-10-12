<template>
  <div class="fc-expenses space-y-4">
    <div class="flex items-center gap-2">
      <h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100">
        Expenses
      </h2>
    </div>

    <FinanceSectionTabs v-model="activeTab" :tabs="TABS" aria-label="Expense views" />

    <ExpenseClaims v-if="activeTab === 'claims'" />
    <EmployeeAdvances v-else-if="activeTab === 'advances'" />
    <ExpenseJournals v-else-if="activeTab === 'journals'" />
  </div>
</template>

<script setup>
import FinanceSectionTabs from '../components/FinanceSectionTabs.vue'
import { ref } from 'vue'
import ExpenseClaims from './expenses/ExpenseClaims.vue'
import EmployeeAdvances from './expenses/EmployeeAdvances.vue'
import ExpenseJournals from './expenses/ExpenseJournals.vue'

const TABS = [
  { key: 'claims', label: 'Expense Claims' },
  { key: 'advances', label: 'Employee Advances' },
  { key: 'journals', label: 'Expense Journals' },
]

const activeTab = ref('claims')
</script>
