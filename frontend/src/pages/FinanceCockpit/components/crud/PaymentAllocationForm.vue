<template>
  <div class="fc-payment-form pb-24">
    <!-- FC-11: Review panel (in-place transition) -->
    <template v-if="reviewing">
      <div class="mb-5">
        <p class="text-xs font-medium text-ink-gray-5">Review Payment</p>
        <h2 class="text-xl font-bold text-ink-gray-9">Confirm Payment</h2>
      </div>

      <div
        v-if="reviewError"
        class="mb-4 rounded-lg border border-red-300 bg-red-50 text-red-700 dark:bg-red-500/10 dark:border-red-500/30 dark:text-red-400 text-sm px-4 py-3 flex items-start gap-2 whitespace-pre-line"
      >
        <FcIcon name="alert-circle" :size="18" class="mt-0.5 flex-shrink-0" />
        <span>{{ reviewError }}</span>
      </div>
      <div
        v-if="paymentContextError || paymentContext?.message"
        class="mb-4 rounded-lg border border-amber-300 bg-amber-50 text-amber-800 dark:bg-amber-500/10 dark:border-amber-500/30 dark:text-amber-300 text-sm px-4 py-3"
        role="status"
      >
        {{ paymentContextError || paymentContext.message }}
      </div>

      <SectionCard title="Payment Summary" icon="banknote" tone="positive">
        <dl class="divide-y divide-outline-gray-1">
          <div class="flex items-center justify-between py-2.5">
            <dt class="text-xs font-medium text-ink-gray-5">Customer</dt>
            <dd class="text-sm font-medium text-ink-gray-8">{{ customer }}</dd>
          </div>
          <div class="flex items-center justify-between py-2.5">
            <dt class="text-xs font-medium text-ink-gray-5">Amount</dt>
            <dd class="text-sm font-bold text-ink-gray-9 tabular-nums">
              {{ formatCurrency(totalAllocated, activeCurrency) }}
            </dd>
          </div>
          <div class="flex items-center justify-between py-2.5">
            <dt class="text-xs font-medium text-ink-gray-5">Mode</dt>
            <dd class="text-sm text-ink-gray-8">{{ modeOfPayment || '—' }}</dd>
          </div>
          <div
            v-if="paymentContext?.configured"
            class="flex items-center justify-between py-2.5"
          >
            <dt class="text-xs font-medium text-ink-gray-5">Posting account</dt>
            <dd class="text-sm text-ink-gray-8">
              {{ paymentContext.account }} · {{ paymentContext.account_type }}
            </dd>
          </div>
          <div
            v-if="refFields.refNo"
            class="flex items-center justify-between py-2.5"
          >
            <dt class="text-xs font-medium text-ink-gray-5">
              {{ refFields.refNo }}
            </dt>
            <dd class="text-sm text-ink-gray-8">{{ referenceNo || '—' }}</dd>
          </div>
          <div
            v-if="refFields.refDate"
            class="flex items-center justify-between py-2.5"
          >
            <dt class="text-xs font-medium text-ink-gray-5">
              {{ refFields.refDate }}
            </dt>
            <dd class="text-sm text-ink-gray-8">{{ referenceDate || '—' }}</dd>
          </div>
          <div class="flex items-center justify-between py-2.5">
            <dt class="text-xs font-medium text-ink-gray-5">Date</dt>
            <dd class="text-sm text-ink-gray-8">{{ postingDate }}</dd>
          </div>
        </dl>
      </SectionCard>

      <SectionCard
        title="Allocations"
        icon="receipt"
        class="mt-4"
        tone="positive"
        :badge="selectedRows.length"
      >
        <div class="divide-y divide-outline-gray-1">
          <div
            v-for="row in selectedRows"
            :key="row.name"
            class="flex items-center justify-between py-2.5"
          >
            <span class="text-sm font-medium text-ink-gray-8">{{
              row.name
            }}</span>
            <span class="text-sm tabular-nums text-ink-gray-7">{{
              formatCurrency(row._allocated, activeCurrency)
            }}</span>
          </div>
        </div>
        <div
          class="mt-3 pt-3 border-t border-outline-gray-1 flex items-center justify-between text-sm"
        >
          <span class="text-ink-gray-5">Unallocated</span>
          <span
            class="tabular-nums"
            :class="
              unallocated > 0.005
                ? 'text-amber-600 font-medium'
                : 'text-ink-gray-7'
            "
          >
            {{ formatCurrency(unallocated, activeCurrency) }}
          </span>
        </div>
      </SectionCard>

      <!-- Success state -->
      <div
        v-if="successPe"
        class="mt-4 rounded-lg border border-outline-green-1 bg-surface-green-1 px-4 py-3 flex items-center justify-between"
      >
        <span class="text-sm font-medium text-ink-green-7"
          >{{ successPe }} sent for approval</span
        >
        <a
          :href="cockpitRecordHref('Payment Entry', successPe, company)"
          class="text-xs text-ink-green-6 hover:underline font-medium"
          >Open Payment Entry →</a
        >
      </div>
      <div
        v-if="integrationWarning"
        class="mt-3 rounded-lg border border-outline-amber-2 bg-surface-amber-1 px-4 py-3 text-sm text-ink-amber-8 whitespace-pre-line"
        role="status"
      >
        {{ integrationWarning }}
      </div>
    </template>

    <!-- Main form -->
    <template v-else>
      <div class="mb-5">
        <p class="text-xs font-medium text-ink-gray-5">New Document</p>
        <h2 class="text-xl font-bold text-ink-gray-9">
          {{ isMappedPayment ? 'Create Invoice Payment' : 'Receive Payment' }}
        </h2>
        <p class="text-sm text-ink-gray-5 mt-0.5">
          <template v-if="isMappedPayment">
            Review the payment for {{ mappedInvoiceId }}. The allocation stays within its current outstanding amount.
          </template>
          <template v-else>
          Record a customer receipt and allocate it across outstanding invoices.
          </template>
        </p>
      </div>

      <!-- Error banner (non-review) -->
      <div
        v-if="errorMsg"
        class="mb-4 rounded-lg border border-red-300 bg-red-50 text-red-700 dark:bg-red-500/10 dark:border-red-500/30 dark:text-red-400 text-sm px-4 py-3 flex items-start gap-2 whitespace-pre-line"
      >
        <FcIcon name="alert-circle" :size="18" class="mt-0.5 flex-shrink-0" />
        <span>{{ errorMsg }}</span>
      </div>

      <div
        v-if="paymentContextError || paymentContext?.message"
        class="mb-4 rounded-lg border border-amber-300 bg-amber-50 text-amber-800 dark:bg-amber-500/10 dark:border-amber-500/30 dark:text-amber-300 text-sm px-4 py-3"
        role="status"
      >
        {{ paymentContextError || paymentContext.message }}
      </div>
      <div
        v-else-if="paymentContext?.configured"
        class="mb-4 rounded-lg border border-outline-gray-1 bg-surface-gray-1 text-ink-gray-6 text-xs px-4 py-2.5"
      >
        Posting to {{ paymentContext.account }} · {{ paymentContext.account_type }} account
        <span v-if="paymentContext.requires_reference"> · Reference number and date required</span>
      </div>

      <form class="space-y-5" @submit.prevent>
        <!-- Payment details -->
        <SectionCard title="Payment Details" icon="banknote" tone="positive">
          <div class="grid grid-cols-1 md:grid-cols-2 gap-x-5 gap-y-4">
            <!-- FC-08: Customer smart search (name + customer_name) -->
            <div class="md:col-span-2">
              <label class="block text-xs font-medium text-ink-gray-6 mb-1">
                Customer<span class="text-red-500 ml-0.5">*</span>
              </label>
              <div
                v-if="isMappedPayment"
                class="rounded-lg border border-outline-gray-2 bg-surface-gray-1 px-3 py-2 text-sm text-ink-gray-8"
              >
                {{ customer || 'Unavailable' }}
              </div>
              <Combobox
                v-else
                :model-value="customer"
                :options="customerOptions"
                :filterable="false"
                placeholder="Search customer..."
                @update:model-value="onCustomerChange"
                @update:query="onCustomerQuery"
              />
              <p
                v-if="customerSearchLoading"
                class="mt-1.5 text-xs text-ink-gray-5"
                role="status"
              >
                Searching eligible customers for {{ company }}…
              </p>
              <p
                v-else-if="customerSearchError"
                class="mt-1.5 text-xs text-red-600"
                role="alert"
              >
                {{ customerSearchError }}
              </p>
              <p
                v-else-if="!isMappedPayment && !customerOptions.length"
                class="mt-1.5 text-xs text-ink-gray-5"
                role="status"
              >
                No customers with outstanding invoices in {{ company }}.
              </p>
              <!-- FC-08: Balance chip -->
              <div
                v-if="customer && customerBalance !== null"
                class="mt-1.5 text-xs text-ink-gray-5"
              >
                <span class="inline-flex items-center gap-1">
                  <span class="font-medium text-ink-gray-7">{{
                    formatCurrency(customerBalance, activeCurrency)
                  }}</span>
                  outstanding
                  <span v-if="customerInvoiceCount > 0"
                    >({{ customerInvoiceCount }}
                    {{
                      customerInvoiceCount === 1 ? 'invoice' : 'invoices'
                    }})</span
                  >
                </span>
              </div>
            </div>

            <!-- FC-09: Amount received input -->
            <div class="md:col-span-2">
              <label class="block text-xs font-medium text-ink-gray-6 mb-1"
                >Amount Received</label
              >
              <div class="flex items-center gap-2">
                <div class="flex items-center gap-1.5 flex-1">
                  <span
                    v-if="activeCurrency"
                    class="text-xs font-medium text-ink-gray-5 w-8 text-right flex-shrink-0"
                    >{{ activeCurrency }}</span
                  >
                  <input
                    type="number"
                    min="0"
                    step="any"
                    class="flex-1 text-sm rounded-lg border border-outline-gray-2 bg-surface-white px-3 py-2 text-ink-gray-8 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    :value="paidAmount"
                    placeholder="0.00"
                    @input="
                      paidAmount = parseFloat($event.target.value) || null
                    "
                  />
                </div>
                <button
                  v-if="canAutoAllocate"
                  type="button"
                  class="text-xs font-medium text-blue-600 border border-outline-gray-2 rounded-lg px-3 py-2 hover:bg-surface-gray-1 transition-colors whitespace-nowrap"
                  @click="autoAllocate"
                >
                  Auto-Allocate
                </button>
              </div>
            </div>

            <div>
              <label class="block text-xs font-medium text-ink-gray-6 mb-1"
                >Posting Date</label
              >
              <DatePicker
                :model-value="postingDate"
                @update:model-value="postingDate = $event"
              />
            </div>

            <!-- FC-07: Mode of Payment pill group -->
            <div>
              <label class="block text-xs font-medium text-ink-gray-6 mb-1"
                >Mode of Payment</label
              >
              <div class="flex flex-wrap gap-1.5">
                <button
                  v-for="mode in visibleModes"
                  :key="mode"
                  type="button"
                  class="text-xs font-medium px-3 py-1.5 rounded-full border transition-colors"
                  :class="
                    modeOfPayment === mode
                      ? 'bg-surface-gray-4 border-outline-gray-3 text-ink-gray-9'
                      : 'bg-surface-white border-outline-gray-2 text-ink-gray-6 hover:bg-surface-gray-1'
                  "
                  @click="selectMode(mode)"
                >
                  {{ mode }}
                </button>
                <div class="relative">
                  <button
                    type="button"
                    class="text-xs font-medium px-3 py-1.5 rounded-full border border-outline-gray-2 bg-surface-white text-ink-gray-6 hover:bg-surface-gray-1 transition-colors"
                    :class="moreOpen ? 'bg-surface-gray-1' : ''"
                    @click="moreOpen = !moreOpen"
                  >
                    + More ▾
                  </button>
                  <div
                    v-if="moreOpen"
                    class="absolute left-0 mt-1 z-20 bg-surface-white border border-outline-gray-2 rounded-xl shadow-lg min-w-[160px] py-1"
                  >
                    <Combobox
                      :model-value="null"
                      :options="extraModeOptions"
                      :filterable="false"
                      placeholder="Search mode..."
                      class="p-2"
                      @update:model-value="selectMode"
                      @update:query="onModeQuery"
                    />
                  </div>
                </div>
              </div>
              <p v-if="!modeOfPayment" class="mt-1.5 text-xs text-ink-gray-5">
                Choose a mode to resolve its account for the active company.
              </p>
            </div>

            <!-- FC-12: Reference labels adapt to payment mode -->
            <template v-if="refFields.refNo">
              <FormControl
                type="text"
                :label="refFields.refNo"
                :model-value="referenceNo"
                @update:model-value="referenceNo = $event"
              />
            </template>
            <div v-if="refFields.refDate">
              <label class="block text-xs font-medium text-ink-gray-6 mb-1">{{
                refFields.refDate
              }}</label>
              <DatePicker
                :model-value="referenceDate"
                @update:model-value="referenceDate = $event"
              />
            </div>
          </div>
        </SectionCard>

        <!-- Outstanding invoices — FC-10: sort, Select All, overdue -->
        <SectionCard
          title="Allocate to Invoices"
          icon="receipt"
          hero
          :badge="selectedCount || ''"
        >
          <div
            v-if="!customer"
            class="text-sm text-ink-gray-5 py-6 text-center"
          >
            Select a customer to load their outstanding invoices.
          </div>

          <div v-else-if="invoicesLoading" class="space-y-2">
            <div
              v-for="n in 4"
              :key="n"
              class="h-11 bg-surface-gray-2 rounded-lg animate-pulse"
            />
          </div>

          <div
            v-else-if="!invoices.length"
            class="text-sm text-ink-gray-5 py-6 text-center"
          >
            No outstanding invoices for this customer.
          </div>

          <div v-else class="overflow-x-auto -mx-1">
            <!-- FC-09: Footer bar above table -->
            <div
              v-if="paidAmount"
              class="mb-2 flex items-center gap-4 text-xs text-ink-gray-5 px-1"
            >
              <span
                >Allocated
                <span class="font-semibold text-ink-gray-8 tabular-nums">{{
                  formatCurrency(totalAllocated, activeCurrency)
                }}</span></span
              >
              <span class="text-outline-gray-3">|</span>
              <span
                :class="unallocated > 0.005 ? 'text-amber-600 font-medium' : ''"
              >
                Unallocated
                <span class="font-semibold tabular-nums">{{
                  formatCurrency(unallocated, activeCurrency)
                }}</span>
              </span>
              <span class="text-outline-gray-3">|</span>
              <span
                >Total
                <span class="font-semibold text-ink-gray-8 tabular-nums">{{
                  formatCurrency(paidAmount || 0, activeCurrency)
                }}</span></span
              >
            </div>
            <table class="w-full text-sm">
              <thead>
                <tr
                  class="text-left text-xs font-semibold text-ink-gray-5 uppercase tracking-wide border-b border-outline-gray-1"
                >
                  <!-- FC-10: Select All checkbox -->
                  <th class="px-2 py-2 w-8">
                    <input
                      type="checkbox"
                      class="rounded border-outline-gray-3 text-blue-600 focus:ring-blue-500"
                      :checked="allSelected"
                      :indeterminate="someSelected && !allSelected"
                      @change="toggleAll($event.target.checked)"
                    />
                  </th>
                  <!-- FC-10: Sortable column headers -->
                  <th
                    class="px-2 py-2 cursor-pointer hover:text-ink-gray-8 select-none"
                    @click="setSort('name')"
                  >
                    Invoice
                    <span class="ml-0.5">{{ sortIndicator('name') }}</span>
                  </th>
                  <th
                    class="px-2 py-2 cursor-pointer hover:text-ink-gray-8 select-none"
                    @click="setSort('due_date')"
                  >
                    Due
                    <span class="ml-0.5">{{ sortIndicator('due_date') }}</span>
                  </th>
                  <th
                    class="px-2 py-2 text-right cursor-pointer hover:text-ink-gray-8 select-none"
                    @click="setSort('outstanding_amount')"
                  >
                    Outstanding
                    <span class="ml-0.5">{{
                      sortIndicator('outstanding_amount')
                    }}</span>
                  </th>
                  <th class="px-2 py-2 text-right w-40">Allocate</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in sortedInvoices"
                  :key="row.name"
                  class="border-b border-outline-gray-1 last:border-0"
                  :class="
                    row._selected ? 'bg-blue-50/50 dark:bg-blue-500/5' : ''
                  "
                >
                  <td class="px-2 py-2">
                    <input
                      type="checkbox"
                      class="rounded border-outline-gray-3 text-blue-600 focus:ring-blue-500"
                      :checked="row._selected"
                      @change="toggleRow(row, $event.target.checked)"
                    />
                  </td>
                  <td class="px-2 py-2">
                    <span class="font-medium text-ink-gray-8">{{
                      row.name
                    }}</span>
                    <span
                      v-if="row.days_overdue > 0"
                      class="ml-1.5 text-xs text-red-500 dark:text-red-400"
                      >{{ row.days_overdue }}d overdue</span
                    >
                  </td>
                  <!-- FC-10: overdue date cell in red -->
                  <td
                    class="px-2 py-2"
                    :class="
                      row.days_overdue > 0
                        ? 'text-red-500 dark:text-red-400'
                        : 'text-ink-gray-6'
                    "
                  >
                    {{ row.due_date || '—' }}
                  </td>
                  <td class="px-2 py-2 text-right tabular-nums text-ink-gray-7">
                    {{ formatCurrency(row.outstanding_amount, row.currency) }}
                  </td>
                  <td class="px-2 py-2 text-right">
                    <input
                      type="number"
                      min="0"
                      :max="row.outstanding_amount"
                      step="any"
                      class="w-32 text-right text-sm rounded-lg border border-outline-gray-2 bg-surface-white px-2 py-1 tabular-nums disabled:bg-surface-gray-2 disabled:text-ink-gray-4"
                      :disabled="!row._selected"
                      :value="row._allocated"
                      @input="onAllocInput(row, $event.target.value)"
                    />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </SectionCard>
      </form>
    </template>

    <!-- Sticky action bar -->
    <div
      class="fixed bottom-0 inset-x-0 z-30 bg-surface-white/95 backdrop-blur border-t border-outline-gray-2"
    >
      <div
        class="max-w-screen-2xl mx-auto px-6 py-3 flex items-center justify-between gap-3"
      >
        <div class="hidden sm:flex items-center gap-2 text-sm text-ink-gray-5">
          <span>Total Allocated</span>
          <span class="text-base font-bold text-ink-gray-9 tabular-nums">{{
            formatCurrency(totalAllocated, activeCurrency)
          }}</span>
        </div>
        <div class="flex items-center gap-2 ml-auto">
          <Button
            variant="outline"
            theme="gray"
            :label="reviewing ? '← Back to Edit' : 'Cancel'"
            @click="onBack"
          />
          <Button
            v-if="reviewing"
            variant="solid"
            theme="blue"
            :loading="saving"
            :disabled="!canReview || !!successPe"
            @click="onConfirmPost"
          >
            <template #prefix><FcIcon name="send" :size="15" /></template>
            Send for Approval
          </Button>
          <Button
            v-else
            variant="solid"
            theme="blue"
            :disabled="!canReview"
            @click="reviewing = true"
          >
            Review →
          </Button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import {
  Button,
  FormControl,
  Combobox,
  DatePicker,
  createResource,
  debounce,
  toast,
} from 'frappe-ui'
import SectionCard from './SectionCard.vue'
import FcIcon from './FcIcon.vue'
import { useCompanyContext } from '../../composables/useCompanyContext.js'
import { useCurrency } from '../../composables/useCurrency.js'
import { readableError } from '../../composables/financeErrors.js'
import { cockpitRecordHref } from '../../composables/useFinanceNavigation.js'
import {
  clampInvoiceAllocation,
  resolveMappedInvoicePayment,
} from './paymentAllocationSeed.js'

const props = defineProps({
  seed: { type: Object, default: null },
})
const emit = defineEmits(['saved', 'close'])
const isMappedPayment = computed(() => !!props.seed)

const { company } = useCompanyContext()
const { formatCurrency } = useCurrency()

const MOP_STORAGE_KEY = 'fc_recent_modes'
const DEFAULT_MODES = ['Cash', 'Bank Transfer']

function localToday() {
  const d = new Date()
  const off = d.getTimezoneOffset() * 60000
  return new Date(d.getTime() - off).toISOString().slice(0, 10)
}

const customer = ref(null)
const postingDate = ref(localToday())
const modeOfPayment = ref('')
const paymentContext = ref(null)
const paymentContextLoading = ref(false)
const paymentContextError = ref('')
const paymentContextCompany = ref('')
const referenceNo = ref('')
const referenceDate = ref('')
const paidAmount = ref(null)
const saving = ref(false)
const errorMsg = ref('')
const invoices = ref([])
const mappedInvoiceId = ref('')
const mappedSeedRejected = ref(false)
const reviewing = ref(false)
const reviewError = ref('')
const successPe = ref('')
const integrationWarning = ref('')

// FC-10: sort state (default: due_date asc — oldest first)
const sortField = ref('due_date')
const sortAsc = ref(true)

function setSort(field) {
  if (sortField.value === field) {
    sortAsc.value = !sortAsc.value
  } else {
    sortField.value = field
    sortAsc.value = true
  }
}
function sortIndicator(field) {
  if (sortField.value !== field) return ''
  return sortAsc.value ? '▲' : '▼'
}

const sortedInvoices = computed(() => {
  const arr = invoices.value.slice()
  const f = sortField.value
  return arr.sort((a, b) => {
    const av = a[f] ?? ''
    const bv = b[f] ?? ''
    if (av < bv) return sortAsc.value ? -1 : 1
    if (av > bv) return sortAsc.value ? 1 : -1
    return 0
  })
})

const allSelected = computed(
  () => invoices.value.length > 0 && invoices.value.every((r) => r._selected),
)
const someSelected = computed(() => invoices.value.some((r) => r._selected))

function toggleAll(checked) {
  invoices.value.forEach((r) => {
    r._selected = checked
    r._allocated = checked ? Number(r.outstanding_amount) : 0
  })
}

/* ---- FC-07: Mode of Payment pill group ---- */
const recentModes = ref(
  (() => {
    try {
      return JSON.parse(localStorage.getItem(MOP_STORAGE_KEY) || '[]')
    } catch {
      return []
    }
  })(),
)
const allLoadedModes = ref([])
const moreOpen = ref(false)
const modeSearchResults = ref([])
const modeRes = createResource({ url: 'frappe.client.get_list' })

const visibleModes = computed(() => {
  const recent = recentModes.value.length ? recentModes.value : DEFAULT_MODES
  return recent.slice(0, 4)
})

const extraModeOptions = computed(() => {
  const base = modeSearchResults.value.length
    ? modeSearchResults.value
    : allLoadedModes.value
  return base
    .filter((m) => !visibleModes.value.includes(m))
    .map((m) => ({ label: m, value: m }))
})

const onModeQuery = debounce(async (q) => {
  const rows = await modeRes.submit({
    doctype: 'Mode of Payment',
    filters: q ? JSON.stringify([['name', 'like', `%${q}%`]]) : '[]',
    fields: JSON.stringify(['name']),
    limit_page_length: 20,
    order_by: 'name asc',
  })
  modeSearchResults.value = (rows || []).map((r) => r.name)
}, 200)

function selectMode(mode) {
  if (!mode) return
  modeOfPayment.value = mode
  const updated = [mode, ...recentModes.value.filter((m) => m !== mode)].slice(
    0,
    4,
  )
  recentModes.value = updated
  try {
    localStorage.setItem(MOP_STORAGE_KEY, JSON.stringify(updated))
  } catch {
    /* ignore */
  }
  moreOpen.value = false
  loadPaymentContext(mode)
}

const paymentContextRes = createResource({
  url: 'crm.finance.api.get_customer_payment_context',
})
let paymentContextRequest = 0

async function loadPaymentContext(mode = modeOfPayment.value) {
  const request = ++paymentContextRequest
  const requestedCompany = company.value
  paymentContextError.value = ''
  paymentContext.value = null
  paymentContextCompany.value = ''
  if (!mode || !requestedCompany) {
    paymentContextLoading.value = false
    return
  }
  paymentContextLoading.value = true
  try {
    const result = await paymentContextRes.submit({
      company: requestedCompany,
      mode_of_payment: mode,
    })
    if (request !== paymentContextRequest || requestedCompany !== company.value) return
    paymentContext.value = result
    paymentContextCompany.value = requestedCompany
    if (result?.configured && result.account_type === 'Cash') {
      referenceNo.value = ''
      referenceDate.value = ''
    }
  } catch (err) {
    if (request === paymentContextRequest && requestedCompany === company.value) {
      paymentContextError.value = readableError(err)
    }
  } finally {
    if (request === paymentContextRequest) paymentContextLoading.value = false
  }
}

watch(company, () => {
  if (props.seed && props.seed.company !== company.value) {
    mappedSeedRejected.value = true
    errorMsg.value = 'The active company changed. Close this payment and prepare it again from the invoice.'
    customer.value = null
    invoices.value = []
    invoicesCompany.value = ''
    paidAmount.value = null
    reviewing.value = false
    paymentContext.value = null
    paymentContextCompany.value = ''
    return
  }
  // A company switch invalidates the entire draft so no old-company balance,
  // allocation, or resolved account can be posted under the new context.
  invoiceRequest += 1
  customerRequest += 1
  customer.value = null
  customerResults.value = []
  customerSearchLoading.value = false
  customerSearchError.value = ''
  invoices.value = []
  invoicesCompany.value = ''
  invoicesLoading.value = false
  customerBalance.value = null
  customerInvoiceCount.value = 0
  paidAmount.value = null
  referenceNo.value = ''
  referenceDate.value = ''
  reviewing.value = false
  reviewError.value = ''
  errorMsg.value = ''
  successPe.value = ''
  loadPaymentContext()
  onCustomerQuery('')
})

// Native Payment Entry requires both transaction references only for Bank accounts.
const refFields = computed(() => {
  if (!paymentContext.value?.configured || !paymentContext.value.requires_reference) {
    return { refNo: null, refDate: null }
  }
  return { refNo: 'Reference No. *', refDate: 'Reference Date *' }
})

/* ---- FC-08: Customer smart search ---- */
const customerResults = ref([])
const customerOptionsRes = createResource({
  url: 'crm.finance.api.get_customer_payment_options',
})
let customerRequest = 0
const customerSearchLoading = ref(false)
const customerSearchError = ref('')
const customerOptions = computed(() => {
  const opts = customerResults.value.slice()
  if (customer.value && !opts.some((o) => o.value === customer.value)) {
    opts.unshift({ label: customer.value, value: customer.value })
  }
  return opts
})
const fetchCustomerOptions = debounce(async (searchTerm, request, requestedCompany) => {
  try {
    const rows = await customerOptionsRes.submit({
      company: requestedCompany,
      search_term: searchTerm,
    })
    if (request !== customerRequest || requestedCompany !== company.value) return
    customerResults.value = rows || []
  } catch (err) {
    if (request === customerRequest && requestedCompany === company.value) {
      customerResults.value = []
      customerSearchError.value = readableError(err)
    }
  } finally {
    if (request === customerRequest) customerSearchLoading.value = false
  }
}, 250)
function onCustomerQuery(query) {
  const request = ++customerRequest
  const requestedCompany = company.value
  customerResults.value = []
  customerSearchError.value = ''
  if (!requestedCompany) {
    customerSearchLoading.value = false
    return
  }
  customerSearchLoading.value = true
  fetchCustomerOptions(String(query || '').trim(), request, requestedCompany)
}

/* ---- FC-08: Customer balance chip ---- */
const customerBalance = ref(null)
const customerInvoiceCount = ref(0)

/* ---- Outstanding invoices ---- */
const invoicesRes = createResource({
  url: 'crm.finance.api.get_customer_outstanding_invoices',
})
const invoicesLoading = ref(false)
const invoicesCompany = ref('')
let invoiceRequest = 0

async function onCustomerChange(val) {
  const request = ++invoiceRequest
  const requestedCompany = company.value
  customer.value = val
  invoices.value = []
  invoicesCompany.value = ''
  invoicesLoading.value = false
  customerBalance.value = null
  customerInvoiceCount.value = 0
  paidAmount.value = null
  // FC-07: do NOT reset modeOfPayment on customer change (spec FC-07: delete line 231).
  referenceNo.value = ''
  referenceDate.value = ''
  if (!val || !requestedCompany) return
  invoicesLoading.value = true
  errorMsg.value = ''
  try {
    const rows = await invoicesRes.submit({
      company: requestedCompany,
      customer: val,
    })
    if (
      request !== invoiceRequest ||
      requestedCompany !== company.value ||
      customer.value !== val
    ) return
    invoices.value = (rows || []).map((r) => ({
      ...r,
      _selected: false,
      _allocated: 0,
    }))
    if (mappedInvoiceId.value) {
      const mappedInvoice = invoices.value.find(
        (invoice) => invoice.name === mappedInvoiceId.value,
      )
      invoices.value = mappedInvoice ? [mappedInvoice] : []
      if (!mappedInvoice) {
        errorMsg.value = `Invoice ${mappedInvoiceId.value} is no longer outstanding for ${val}. Refresh the invoice and prepare the payment again.`
      }
    }
    // Compute balance chip values.
    customerInvoiceCount.value = invoices.value.length
    customerBalance.value = invoices.value.reduce(
      (s, r) => s + Number(r.outstanding_amount || 0),
      0,
    )
    invoicesCompany.value = requestedCompany
  } catch (err) {
    if (request === invoiceRequest && requestedCompany === company.value) {
      errorMsg.value = readableError(err)
    }
  } finally {
    if (request === invoiceRequest) invoicesLoading.value = false
  }
}

function toggleRow(row, checked) {
  row._selected = checked
  row._allocated = checked ? Number(row.outstanding_amount) : 0
}
function onAllocInput(row, raw) {
  row._allocated = clampInvoiceAllocation(raw, row.outstanding_amount)
}

/* ---- FC-09: Auto-allocate ---- */
const canAutoAllocate = computed(
  () => !!customer.value && paidAmount.value > 0 && invoices.value.length > 0,
)

function autoAllocate() {
  let remaining = Number(paidAmount.value) || 0
  // Sort by due_date asc to fill oldest first.
  const byDue = invoices.value
    .slice()
    .sort((a, b) => ((a.due_date || '') < (b.due_date || '') ? -1 : 1))
  byDue.forEach((row) => {
    if (remaining <= 0) {
      row._selected = false
      row._allocated = 0
      return
    }
    const avail = Number(row.outstanding_amount)
    const alloc = Math.min(avail, remaining)
    row._selected = alloc > 0
    row._allocated = alloc
    remaining -= alloc
  })
}

const selectedRows = computed(() =>
  invoices.value.filter((r) => r._selected && Number(r._allocated) > 0),
)
const selectedCount = computed(() => selectedRows.value.length)
const totalAllocated = computed(() =>
  selectedRows.value.reduce((s, r) => s + Number(r._allocated || 0), 0),
)
const activeCurrency = computed(() => invoices.value[0]?.currency || '')
const unallocated = computed(() =>
  Math.max(0, (paidAmount.value || 0) - totalAllocated.value),
)
const canReview = computed(
  () =>
    !!customer.value &&
    invoicesCompany.value === company.value &&
    paymentContextCompany.value === company.value &&
    !invoicesLoading.value &&
    totalAllocated.value > 0 &&
    !!paymentContext.value?.configured &&
    !paymentContextLoading.value &&
    !mappedSeedRejected.value &&
    (!paymentContext.value.requires_reference ||
      (!!referenceNo.value.trim() && !!referenceDate.value)) &&
    !saving.value,
)

async function initializeMappedPayment() {
  const mapped = resolveMappedInvoicePayment(props.seed, company.value)
  if (mapped.error) {
    mappedSeedRejected.value = true
    errorMsg.value = mapped.error
    return
  }

  mappedInvoiceId.value = mapped.invoice
  customer.value = mapped.customer
  postingDate.value = mapped.postingDate || localToday()
  modeOfPayment.value = mapped.modeOfPayment
  paidAmount.value = mapped.amount

  await onCustomerChange(mapped.customer)
  if (errorMsg.value) {
    mappedSeedRejected.value = true
    return
  }

  const invoice = invoices.value.find((row) => row.name === mapped.invoice)
  if (!invoice) return
  if (mapped.amount > Number(invoice.outstanding_amount) + 0.005) {
    mappedSeedRejected.value = true
    errorMsg.value = `Invoice ${mapped.invoice}'s outstanding amount changed since the payment was prepared. Refresh the invoice and try again.`
    return
  }
  const allocationAmount = clampInvoiceAllocation(
    mapped.amount,
    invoice.outstanding_amount,
  )
  paidAmount.value = allocationAmount
  referenceNo.value = mapped.referenceNo
  referenceDate.value = mapped.referenceDate
  invoice._selected = true
  invoice._allocated = allocationAmount
  if (mapped.modeOfPayment) await loadPaymentContext(mapped.modeOfPayment)
}

function onBack() {
  if (reviewing.value) {
    reviewing.value = false
    reviewError.value = ''
  } else {
    emit('close')
  }
}

const createRes = createResource({
  url: 'crm.finance.api.create_customer_payment',
})

async function onConfirmPost() {
  if (!canReview.value) return
  const submittedCompany = company.value
  saving.value = true
  reviewError.value = ''
  try {
    const allocations = selectedRows.value.map((r) => ({
      invoice: r.name,
      amount: Number(r._allocated),
    }))
    const res = await createRes.submit({
      company: submittedCompany,
      customer: customer.value,
      mode_of_payment: modeOfPayment.value || undefined,
      posting_date: postingDate.value || undefined,
      reference_no: referenceNo.value || undefined,
      reference_date: referenceDate.value || undefined,
      allocations: JSON.stringify(allocations),
      submit: 1,
    })
    integrationWarning.value = (res?.integration_warnings || []).join('\n')
    if (submittedCompany !== company.value) {
      toast.success(
        `Payment ${res?.name || ''} sent for approval in ${submittedCompany}${integrationWarning.value ? '. CRM follow-up is needed.' : ''}`,
      )
      return
    }
    successPe.value = res?.name || ''
    toast.success(`Payment ${res?.name || ''} sent for approval`)
    emit('saved', res)
  } catch (err) {
    if (submittedCompany === company.value) {
      reviewError.value = readableError(err)
    } else {
      toast.error(`Payment approval request failed for ${submittedCompany}: ${readableError(err)}`)
    }
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  if (props.seed) await initializeMappedPayment()
  else onCustomerQuery('')
  try {
    const rows = await modeRes.submit({
      doctype: 'Mode of Payment',
      fields: JSON.stringify(['name']),
      limit_page_length: 20,
      order_by: 'name asc',
    })
    if (rows && rows.length) allLoadedModes.value = rows.map((r) => r.name)
  } catch {
    allLoadedModes.value = ['Cash', 'Bank Transfer', 'M-Pesa', 'Cheque']
  }
})
</script>
