<template>
  <div class="fc-partner-commission space-y-4">
    <div class="flex items-center gap-2">
      <h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100">
        Network &amp; Commission
      </h2>
    </div>

    <FinanceSectionTabs v-model="activeTab" :tabs="TABS" aria-label="Network and commission views" />

    <RebateVouchers v-if="activeTab === 'rebates'" />
    <SalesCommissions v-else-if="activeTab === 'commissions'" />
  </div>
</template>

<script setup>
import FinanceSectionTabs from '../components/FinanceSectionTabs.vue'
import { ref } from 'vue'
import RebateVouchers from './partner/RebateVouchers.vue'
import SalesCommissions from './partner/SalesCommissions.vue'

const TABS = [
  { key: 'rebates', label: 'Rebate Vouchers' },
  { key: 'commissions', label: 'Sales Commissions' },
]

const activeTab = ref('rebates')
</script>
