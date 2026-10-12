<template>
  <div class="fc-banking space-y-4">
    <div class="flex items-center gap-2">
      <h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100">
        Banking
      </h2>
    </div>

    <FinanceSectionTabs v-model="activeTab" :tabs="TABS" aria-label="Banking views" />

    <BankAccounts v-if="activeTab === 'accounts'" />
    <BankTransactions v-else-if="activeTab === 'transactions'" />
  </div>
</template>

<script setup>
import FinanceSectionTabs from '../components/FinanceSectionTabs.vue'
import { ref } from 'vue'
import BankAccounts from './banking/BankAccounts.vue'
import BankTransactions from './banking/BankTransactions.vue'

const TABS = [
  { key: 'accounts', label: 'Bank Accounts' },
  { key: 'transactions', label: 'Transactions' },
]

const activeTab = ref('accounts')
</script>
