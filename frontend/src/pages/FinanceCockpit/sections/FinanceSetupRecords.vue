<template>
  <div>
    <button v-if="showSingleton" type="button" class="mb-4 text-sm text-ink-blue-6 underline" @click="showSingleton = false">Back to setup</button>
    <FinanceForm v-if="showSingleton" :doctype="config.doctype" :title="config.title" :name="config.doctype" @saved="showSingleton = false" @close="showSingleton = false" />
    <CrudSection
      v-else
      :key="setupKey"
      :doctype="config.doctype"
      :title="config.title"
      :subtitle="config.subtitle"
      :columns="config.columns"
      :list-resource-url="config.resource"
      :list-params="listParams"
      :empty-label="config.emptyLabel"
      :page-size="20"
      :create-roles="['Accounts Manager']"
    />
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useCompanyContext } from '../composables/useCompanyContext.js'
import CrudSection from '../components/crud/CrudSection.vue'
import FinanceForm from '../components/crud/FinanceForm.vue'

const props = defineProps({ setupKey: { type: String, required: true } })
const { company } = useCompanyContext()
const showSingleton = ref(false)

const configurations = {
  accounts: {
    doctype: 'Account', title: 'Chart of Accounts', subtitle: 'Manage accounts for the selected company.',
    columns: [{ key: 'account_name', label: 'Account' }, { key: 'root_type', label: 'Category' }, { key: 'account_currency', label: 'Currency' }],
    fields: ['name', 'account_name', 'root_type', 'account_currency', 'company', 'disabled'], companyField: true,
  },
  'cost-centres': {
    doctype: 'Cost Center', title: 'Cost Centres', subtitle: 'Manage cost centre records for the selected company.',
    columns: [{ key: 'cost_center_name', label: 'Cost Centre' }, { key: 'cost_center_number', label: 'Number' }, { key: 'company', label: 'Company' }],
    fields: ['name', 'cost_center_name', 'cost_center_number', 'company', 'disabled'], companyField: true,
  },
  dimensions: {
    doctype: 'Accounting Dimension', title: 'Accounting Dimensions', subtitle: 'Define dimensions used to analyze accounting records.',
    columns: [{ key: 'label', label: 'Dimension' }, { key: 'fieldname', label: 'Field Name' }, { key: 'document_type', label: 'Reference Type' }],
    fields: ['name', 'label', 'fieldname', 'document_type', 'disabled'],
  },
  taxes: {
    doctype: 'Sales Taxes and Charges Template', title: 'Tax Templates', subtitle: 'Manage sales tax rows and company assignments.',
    columns: [{ key: 'title', label: 'Template' }, { key: 'company', label: 'Company' }, { key: 'tax_category', label: 'Tax Category' }],
    fields: ['name', 'title', 'company', 'tax_category', 'disabled'], companyField: true,
  },
  terms: {
    doctype: 'Payment Terms Template', title: 'Payment Terms', subtitle: 'Set payment schedules used on customer invoices.',
    columns: [{ key: 'template_name', label: 'Template' }, { key: 'allocate_payment_based_on_payment_terms', label: 'Payment Allocation' }],
    fields: ['name', 'template_name', 'allocate_payment_based_on_payment_terms'],
  },
  methods: {
    doctype: 'Mode of Payment', title: 'Payment Methods', subtitle: 'Manage accepted payment methods and company accounts.',
    columns: [{ key: 'mode_of_payment', label: 'Payment Method' }, { key: 'type', label: 'Type' }, { key: 'enabled', label: 'Enabled' }],
    fields: ['name', 'mode_of_payment', 'type', 'enabled'],
  },
  'fiscal-year': {
    doctype: 'Fiscal Year', title: 'Fiscal Years', subtitle: 'Manage fiscal year dates and company assignments.',
    columns: [{ key: 'year', label: 'Year' }, { key: 'year_start_date', label: 'Start Date' }, { key: 'year_end_date', label: 'End Date' }],
    fields: ['name', 'year', 'year_start_date', 'year_end_date', 'disabled'],
  },
  currency: {
    doctype: 'Currency Exchange Settings', title: 'Currency Exchange', subtitle: 'Configure the exchange rate service and response mapping.', singleton: true,
    columns: [], fields: [],
  },
}

const setupKey = computed(() => props.setupKey)
const config = computed(() => configurations[props.setupKey] || configurations.accounts)
watch(setupKey, () => { showSingleton.value = config.value.singleton === true })
watch(() => config.value.singleton, (singleton) => { showSingleton.value = singleton === true }, { immediate: true })

function listParams(page = 0, pageSize = 20) {
  const filters = config.value.companyField && company.value ? [['company', '=', company.value]] : []
  return {
    doctype: config.value.doctype,
    fields: JSON.stringify(config.value.fields),
    filters: JSON.stringify(filters),
    limit_start: page * pageSize,
    limit_page_length: pageSize,
    order_by: 'modified desc',
  }
}
</script>
