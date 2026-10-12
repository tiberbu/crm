<template>
  <div class="fc-payables space-y-4">
    <div class="flex items-center gap-2">
      <h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100">
        Payables
      </h2>
    </div>

    <!-- Sub-tab nav -->
    <FinanceSectionTabs v-model="activeTab" :tabs="TABS" aria-label="Payables views" />

    <!-- Tab panels -->
    <ApInvoices v-if="activeTab === 'invoices'" />
    <PurchaseOrders v-else-if="activeTab === 'orders'" />
    <SupplierPayments v-else-if="activeTab === 'payments'" />
    <Suppliers v-else-if="activeTab === 'suppliers'" />
  </div>
</template>

<script setup>
import FinanceSectionTabs from '../components/FinanceSectionTabs.vue'
import { ref } from 'vue'
import ApInvoices from './payables/ApInvoices.vue'
import PurchaseOrders from './payables/PurchaseOrders.vue'
import SupplierPayments from './payables/SupplierPayments.vue'
import Suppliers from './payables/Suppliers.vue'

const TABS = [
  { key: 'invoices', label: 'AP Invoices' },
  { key: 'orders', label: 'Purchase Orders' },
  { key: 'payments', label: 'Payments' },
  { key: 'suppliers', label: 'Suppliers' },
]

const activeTab = ref('invoices')
</script>
