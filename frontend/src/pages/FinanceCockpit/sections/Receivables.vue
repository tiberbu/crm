<template>
  <div class="fc-receivables space-y-4">
    <div class="flex items-center gap-2">
      <h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100">
        Receivables
      </h2>
    </div>

    <!-- Sub-tab nav -->
    <FinanceSectionTabs v-model="activeTab" :tabs="TABS" aria-label="Receivables views" />

    <!-- Tab panels -->
    <ArInvoices v-if="activeTab === 'invoices'" />
    <SalesOrders v-else-if="activeTab === 'orders'" />
    <CustomerPayments v-else-if="activeTab === 'payments'" />
    <Customers v-else-if="activeTab === 'customers'" />
  </div>
</template>

<script setup>
import FinanceSectionTabs from '../components/FinanceSectionTabs.vue'
import { ref } from 'vue'
import ArInvoices from './receivables/ArInvoices.vue'
import SalesOrders from './receivables/SalesOrders.vue'
import CustomerPayments from './receivables/CustomerPayments.vue'
import Customers from './receivables/Customers.vue'

const TABS = [
  { key: 'invoices', label: 'AR Invoices' },
  { key: 'orders', label: 'Sales Orders' },
  { key: 'payments', label: 'Payments' },
  { key: 'customers', label: 'Customers' },
]

const activeTab = ref('invoices')
</script>
