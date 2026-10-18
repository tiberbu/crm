<script setup>
import { computed, onMounted, ref } from 'vue'
import { call, Dialog } from 'frappe-ui'
import TokenCalculator from '@/components/TokenCalculator.vue'
import {
  facilityLabel,
  findOpenOrder,
  invoiceStatus,
  oisForReference,
  packageLabel,
  paymentFailureMessage,
  referenceFromSearch,
  verificationOutcome,
} from '@/utils/portalOrderState'

function __(text, args) {
  let str =
    typeof window !== 'undefined' && typeof window.__ === 'function'
      ? window.__(text)
      : text
  if (args) {
    for (const key of Object.keys(args)) {
      str = str.replace(`:${key}`, args[key])
    }
  }
  return str
}

// State
const loading = ref(true)
const errorMessage = ref('')
const context = ref({
  user: '',
  ois: [],
  customer_accounts: [],
  token_packages: [],
  calculator_config: {},
})

const activeTab = ref('facilities') // 'facilities' | 'renewal' | 'billing' | 'support'
const selectedFacilityMfl = ref('')
const selectedPortalPackageCode = ref('')
const portalCalculatorDialogOpen = ref(false)
const purchaseBusy = ref(false)
const busyId = ref('')
const notice = ref(null)
const bankTransferOis = ref('')
const copiedMfl = ref('')

// Unified Facilities List (combining Customer Accounts & OIS)
const allFacilities = computed(() => {
  const list = []
  const seenMfl = new Set()

  // 1. Customer Accounts (Modern Self-Onboarded & Managed Facilities)
  for (const account of context.value.customer_accounts || []) {
    for (const fac of account.facilities || []) {
      const mfl = String(fac.mfl_code || '').trim()
      if (mfl && !seenMfl.has(mfl.toLowerCase())) {
        seenMfl.add(mfl.toLowerCase())
        list.push({
          facility_name: fac.facility_name || 'Healthcare Facility',
          mfl_code: mfl,
          keph_level: fac.keph_level || '',
          network: fac.network || account.network || 'CareVerse Network',
          membership_status: fac.membership_status || 'Active',
          go_live: Boolean(fac.go_live),
          deal: fac.deal || account.deal || '',
          customer: fac.customer || account.customer || '',
          organization: account.organization || account.customer || '',
          token_package: fac.token_package || '',
          token_quantity: Number(fac.token_quantity) || 0,
          package_price: fac.package_price,
          package_vat: fac.package_vat,
          package_gross_total: fac.package_gross_total,
          package_currency: fac.package_currency || 'KES',
          source_type: 'customer',
        })
      }
    }
  }

  // 2. Legacy Opt-In Submissions (OIS)
  for (const submission of context.value.ois || []) {
    for (const fac of submission.progress?.facilities || []) {
      const mfl = String(fac.mfl_code || '').trim()
      if (mfl && !seenMfl.has(mfl.toLowerCase())) {
        seenMfl.add(mfl.toLowerCase())
        list.push({
          facility_name: fac.facility_name || 'Healthcare Facility',
          mfl_code: mfl,
          keph_level: fac.keph_level || '',
          network: submission.network_slug || 'CareVerse Network',
          membership_status: fac.membership_status || 'Active',
          go_live: Boolean(fac.network_contact?.go_live),
          deal: '',
          customer: '',
          ois_name: submission.name,
          organization: submission.facility_signatory_name || submission.name,
          token_package: submission.progress?.package?.display_name || '',
          token_quantity: Number(submission.progress?.package?.token_quantity) || 0,
          package_price: submission.progress?.package?.price,
          package_vat: submission.progress?.package?.vat_amount,
          package_gross_total: submission.progress?.package?.gross_total,
          package_currency: submission.progress?.package?.currency || 'KES',
          source_type: 'ois',
        })
      }
    }
  }

  return list
})

// Unified Orders List
const allOrders = computed(() => {
  const list = []
  for (const account of context.value.customer_accounts || []) {
    for (const order of account.open_orders || []) {
      list.push({
        ...order,
        source_type: 'customer',
        customer: order.customer || account.customer,
        organization: account.organization || account.customer,
      })
    }
  }
  for (const submission of context.value.ois || []) {
    for (const order of submission.open_orders || []) {
      list.push({
        ...order,
        source_type: 'ois',
        ois_name: submission.name,
        organization: submission.facility_signatory_name || submission.name,
      })
    }
  }
  return list
})

// Unified Invoices List
const allInvoices = computed(() => {
  const list = []
  for (const account of context.value.customer_accounts || []) {
    for (const invoice of account.open_invoices || []) {
      list.push({
        ...invoice,
        source_type: 'customer',
        customer: invoice.customer || account.customer,
        organization: account.organization || account.customer,
      })
    }
  }
  for (const submission of context.value.ois || []) {
    for (const invoice of submission.open_invoices || []) {
      list.push({
        ...invoice,
        source_type: 'ois',
        ois_name: submission.name,
        organization: submission.facility_signatory_name || submission.name,
      })
    }
  }
  return list
})

// Currently Selected Facility for Renewal / Calculator
const selectedFacility = computed(() => {
  if (selectedFacilityMfl.value) {
    const found = allFacilities.value.find(
      (f) => String(f.mfl_code).toLowerCase() === String(selectedFacilityMfl.value).toLowerCase(),
    )
    if (found) return found
  }
  return allFacilities.value[0] || null
})

// Summary KPI Computations
const facilityCount = computed(() => allFacilities.value.length)

const totalTokenCount = computed(() =>
  allFacilities.value.reduce((sum, fac) => sum + (fac.token_quantity || 0), 0),
)

const pendingOrderCount = computed(
  () => allOrders.value.filter((order) => order.can_create_invoice).length,
)

const openInvoiceCount = computed(() => allInvoices.value.length)

const totalOutstandingAmount = computed(() =>
  allInvoices.value.reduce((sum, inv) => sum + (Number(inv.amount) || 0), 0),
)

const primaryCustomerAccount = computed(
  () => context.value.customer_accounts?.[0] || null,
)

const activeDeals = computed(() => {
  const set = new Set()
  for (const acc of context.value.customer_accounts || []) {
    if (acc.deal) set.add(acc.deal)
    for (const d of acc.deals || []) {
      if (d) set.add(d)
    }
  }
  for (const fac of allFacilities.value) {
    if (fac.deal) set.add(fac.deal)
  }
  return Array.from(set)
})

const defaultCurrency = computed(() => {
  return (
    allInvoices.value[0]?.currency ||
    context.value.token_packages?.[0]?.currency ||
    'KES'
  )
})

// Actions & Helpers
function copyMfl(code) {
  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(code)
    copiedMfl.value = code
    setTimeout(() => {
      if (copiedMfl.value === code) copiedMfl.value = ''
    }, 2000)
  }
}

function selectFacilityForRenewal(fac) {
  selectedFacilityMfl.value = fac.mfl_code
  activeTab.value = 'renewal'
  if (typeof window !== 'undefined') {
    window.scrollTo({ top: 320, behavior: 'smooth' })
  }
}

function openCalculatorForFacility(fac) {
  selectedFacilityMfl.value = fac.mfl_code
  portalCalculatorDialogOpen.value = true
}

function onCalculatorSelectPackage(code) {
  selectedPortalPackageCode.value = code
}

function onCalculatorApplyPlan(pkg) {
  selectedPortalPackageCode.value = pkg.item_code
  portalCalculatorDialogOpen.value = false
  buyPackage(pkg)
}

function existingOrderForSelectedFacility(item) {
  if (!selectedFacility.value) return null
  return findOpenOrder(
    allOrders.value,
    selectedFacility.value.mfl_code,
    item.item_code,
  )
}

function money(value, currency) {
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: currency || defaultCurrency.value || 'KES',
    maximumFractionDigits: 0,
  }).format(value || 0)
}

function unwrap(response) {
  return (
    response?.message?.data ||
    response?.data ||
    response?.message ||
    response ||
    {}
  )
}

async function refreshContext() {
  const refreshed = await call('crm.api.website_redirect.get_portal_context')
  context.value = unwrap(refreshed) || context.value
  if (!selectedFacilityMfl.value && allFacilities.value.length) {
    selectedFacilityMfl.value = allFacilities.value[0].mfl_code
  }
}

async function buyPackage(item) {
  if (!selectedFacility.value) {
    notice.value = {
      tone: 'error',
      text: 'Please select a facility to receive this token package.',
    }
    return
  }

  purchaseBusy.value = true
  notice.value = null

  try {
    const params = {
      facility_mfl: selectedFacility.value.mfl_code,
      package_item_code: item.item_code,
    }
    if (selectedFacility.value.customer) {
      params.customer = selectedFacility.value.customer
    } else if (selectedFacility.value.ois_name) {
      params.ois_number = selectedFacility.value.ois_name
    }

    const payload = unwrap(
      await call('crm.api.customer_experience.create_token_order', params),
    )

    notice.value = {
      tone: 'success',
      text: `Order ${payload.sales_order || ''} successfully generated for ${selectedFacility.value.facility_name}. Review it under Billing & Invoices to create its invoice and proceed.`,
    }

    await refreshContext()
    activeTab.value = 'billing'
  } catch (error) {
    notice.value = {
      tone: 'error',
      text:
        error?.messages?.[0] ||
        error?.message ||
        'We could not create the token order. Please try again.',
    }
  } finally {
    purchaseBusy.value = false
  }
}

async function createInvoice(order) {
  busyId.value = order.name
  notice.value = null
  try {
    await call('crm.api.customer_experience.start_token_payment', {
      sales_order: order.name,
    })
    await refreshContext()
    notice.value = {
      tone: 'success',
      text: `Invoice for order ${order.name} is ready! It is now listed under Open Invoices ready for payment.`,
    }
  } catch (error) {
    notice.value = {
      tone: 'error',
      text:
        error?.messages?.[0] ||
        'We could not create an invoice for this order. Please try again or contact support.',
    }
  } finally {
    busyId.value = ''
  }
}

async function payInvoice(invoice) {
  busyId.value = invoice.name
  notice.value = null
  bankTransferOis.value = ''
  try {
    const params = { invoice: invoice.name }
    if (invoice.ois_name) {
      params.ois_number = invoice.ois_name
    } else if (invoice.customer) {
      params.customer = invoice.customer
    }

    const data = unwrap(
      await call('crm.api.checkout.initialize_portal_paystack_payment', params),
    )

    if (data.authorization_url) {
      window.location.href = data.authorization_url
      return
    }
    notice.value = { tone: 'error', text: 'Payment checkout could not be started.' }
  } catch (error) {
    const failure = paymentFailureMessage(error)
    notice.value = { tone: 'error', text: failure.message }
    if (failure.offerBankTransfer && invoice.ois_name) {
      bankTransferOis.value = invoice.ois_name
    }
  } finally {
    busyId.value = ''
  }
}

async function verifyReturnedPayment() {
  const reference = referenceFromSearch(window.location.search)
  if (!reference) return
  window.history.replaceState({}, '', window.location.pathname)

  const oisName = oisForReference(
    reference,
    (context.value.ois || []).map((item) => item.name),
  )

  try {
    const params = { reference }
    if (oisName) params.ois_number = oisName

    const result = unwrap(
      await call('crm.api.checkout.verify_portal_paystack_payment', params),
    )
    notice.value = verificationOutcome(result)
    if (result.paid) await refreshContext()
  } catch (error) {
    notice.value = {
      tone: 'error',
      text: error?.messages?.[0] || 'We could not confirm the payment yet.',
    }
  }
}

function invoiceUnavailableMessage(order) {
  const status = String(order.status || '').toLowerCase()
  if (status === 'on hold')
    return 'This order is on hold. Contact support if you need help.'
  if (status === 'closed' || status === 'cancelled')
    return 'This order is closed and cannot be invoiced.'
  return 'An invoice is not available for this order.'
}

onMounted(async () => {
  try {
    await refreshContext()
    await verifyReturnedPayment()
  } catch (error) {
    errorMessage.value =
      error?.messages?.[0] || 'We could not load your facility portal.'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <main class="min-h-screen bg-[#f8fafc] text-slate-900 relative isolate">
    <!-- Ambient Backdrop Highlights -->
    <div class="pointer-events-none fixed inset-0 -z-10 overflow-hidden" aria-hidden="true">
      <div class="absolute -top-40 right-1/4 h-96 w-96 rounded-full bg-[radial-gradient(circle,rgba(188,24,35,0.06)_0%,transparent_65%)] blur-2xl"></div>
      <div class="absolute top-1/2 -left-24 h-96 w-96 rounded-full bg-[radial-gradient(circle,rgba(16,185,129,0.05)_0%,transparent_65%)] blur-2xl"></div>
    </div>

    <!-- Header Navigation -->
    <header class="sticky top-0 z-30 border-b border-slate-200/80 bg-white/85 backdrop-blur-md">
      <div class="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6 lg:px-8">
        <div class="flex items-center gap-3">
          <div
            class="flex size-9 items-center justify-center rounded-xl bg-[#bc1823] text-white font-bold text-base shadow-sm"
          >
            T
          </div>
          <div>
            <p class="text-sm font-semibold tracking-tight text-slate-900 flex items-center gap-2">
              <span>Tiberbu</span>
              <span class="rounded bg-red-50 border border-red-200/70 px-1.5 py-0.2 text-[11px] font-semibold text-[#bc1823]">
                CX Portal
              </span>
            </p>
            <p class="text-[11px] font-medium text-slate-500 flex items-center gap-1.5">
              <span class="inline-block size-1.5 rounded-full bg-emerald-500"></span>
              Secure Customer Experience
            </p>
          </div>
        </div>

        <div class="flex items-center gap-3 text-xs sm:text-sm">
          <div
            v-if="context.user"
            class="hidden sm:inline-flex items-center gap-2 rounded-xl bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-700 border border-slate-200"
          >
            <span class="flex size-5 items-center justify-center rounded-full bg-slate-200 text-[10px] font-semibold text-slate-600">
              👤
            </span>
            <span>{{ context.user }}</span>
          </div>
          <a
            class="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-1.5 font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 hover:text-slate-900"
            href="/api/method/logout"
          >
            Sign out
          </a>
        </div>
      </div>
    </header>

    <div class="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 sm:py-8 space-y-6">
      <!-- Executive SaaS Overview Card -->
      <section
        class="relative isolate overflow-hidden rounded-2xl border border-slate-200/90 bg-white p-6 sm:p-8 shadow-sm backdrop-blur-md"
      >
        <div
          class="pointer-events-none absolute -right-16 -top-20 size-64 rounded-full bg-[radial-gradient(circle,rgba(188,24,35,0.08)_0%,transparent_70%)]"
          aria-hidden="true"
        />

        <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
          <div class="space-y-2 max-w-2xl">
            <div class="flex flex-wrap items-center gap-2">
              <span
                class="inline-flex items-center gap-1.5 rounded-full border border-red-200 bg-red-50/80 px-3 py-0.5 text-xs font-semibold uppercase tracking-wider text-[#bc1823]"
              >
                Healthcare Organization
              </span>
              <span
                v-if="primaryCustomerAccount?.network || allFacilities[0]?.network"
                class="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-xs font-medium text-slate-700"
              >
                Network: <strong>{{ primaryCustomerAccount?.network || allFacilities[0]?.network }}</strong>
              </span>
              <span
                v-if="activeDeals.length"
                class="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-800"
              >
                <span>Deal:</span>
                <span v-for="d in activeDeals" :key="d" class="font-mono font-bold">#{{ d }}</span>
              </span>
            </div>

            <h1 class="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">
              {{ primaryCustomerAccount?.organization || context.user || 'Customer Portal' }}
            </h1>
            <p class="text-sm leading-relaxed text-slate-600">
              Manage care token allocations, track active clinical subscriptions, review billing invoices, and simulate clinic volume.
            </p>
          </div>

          <!-- Quick Action Buttons -->
          <div class="flex flex-wrap items-center gap-3 shrink-0">
            <button
              type="button"
              class="inline-flex items-center gap-2 rounded-xl bg-[#bc1823] px-4 py-2.5 text-xs sm:text-sm font-semibold text-white shadow-sm transition hover:bg-[#a3141d]"
              @click="activeTab = 'renewal'"
            >
              <span>🪙</span>
              <span>Renew / Top-Up Tokens</span>
            </button>
            <button
              type="button"
              class="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-xs sm:text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50 hover:text-slate-900"
              @click="portalCalculatorDialogOpen = true"
            >
              <span>🧮</span>
              <span>Sizing Calculator</span>
            </button>
          </div>
        </div>

        <!-- 4 Core Executive Metric Cards -->
        <div
          v-if="!loading && !errorMessage"
          class="mt-8 grid grid-cols-2 gap-3.5 sm:grid-cols-4"
          aria-label="Account metrics"
        >
          <!-- Facilities Card -->
          <div
            class="rounded-xl border border-slate-100 bg-slate-50/70 p-4 shadow-sm transition hover:bg-white hover:border-slate-200 cursor-pointer"
            @click="activeTab = 'facilities'"
          >
            <div class="flex items-center justify-between text-slate-500 mb-1.5">
              <span class="text-[11px] font-bold uppercase tracking-wider text-slate-600">
                Facilities
              </span>
              <span class="text-base">🏥</span>
            </div>
            <p class="text-2xl sm:text-3xl font-bold text-slate-900 leading-none">
              {{ facilityCount }}
            </p>
            <p class="mt-2 text-xs font-medium text-slate-500">
              Connected clinics
            </p>
          </div>

          <!-- Token Balance Card -->
          <div
            class="rounded-xl border border-slate-100 bg-slate-50/70 p-4 shadow-sm transition hover:bg-white hover:border-slate-200 cursor-pointer"
            @click="activeTab = 'renewal'"
          >
            <div class="flex items-center justify-between text-slate-500 mb-1.5">
              <span class="text-[11px] font-bold uppercase tracking-wider text-slate-600">
                Active Tokens
              </span>
              <span class="text-base">🪙</span>
            </div>
            <p class="text-2xl sm:text-3xl font-bold text-[#bc1823] leading-none">
              {{ totalTokenCount.toLocaleString() }}
            </p>
            <p class="mt-2 text-xs font-medium text-slate-500">
              Allocated capacity
            </p>
          </div>

          <!-- Pending Orders Card -->
          <div
            class="rounded-xl border border-slate-100 bg-slate-50/70 p-4 shadow-sm transition hover:bg-white hover:border-slate-200 cursor-pointer"
            @click="activeTab = 'billing'"
          >
            <div class="flex items-center justify-between text-slate-500 mb-1.5">
              <span class="text-[11px] font-bold uppercase tracking-wider text-slate-600">
                Pending Orders
              </span>
              <span class="text-base">📦</span>
            </div>
            <p class="text-2xl sm:text-3xl font-bold text-slate-900 leading-none">
              {{ pendingOrderCount }}
            </p>
            <p class="mt-2 text-xs font-medium text-slate-500">
              Awaiting invoice
            </p>
          </div>

          <!-- Open Invoices Card -->
          <div
            class="rounded-xl border border-slate-100 bg-slate-50/70 p-4 shadow-sm transition hover:bg-white hover:border-slate-200 cursor-pointer"
            @click="activeTab = 'billing'"
          >
            <div class="flex items-center justify-between text-slate-500 mb-1.5">
              <span class="text-[11px] font-bold uppercase tracking-wider text-slate-600">
                Open Invoices
              </span>
              <span class="text-base">💳</span>
            </div>
            <p class="text-2xl sm:text-3xl font-bold leading-none" :class="openInvoiceCount ? 'text-amber-600' : 'text-emerald-600'">
              {{ openInvoiceCount ? money(totalOutstandingAmount) : 'Paid' }}
            </p>
            <p class="mt-2 text-xs font-medium text-slate-500">
              {{ openInvoiceCount ? `${openInvoiceCount} awaiting payment` : 'All invoices settled' }}
            </p>
          </div>
        </div>
      </section>

      <!-- Feedback / Notification Banner -->
      <div
        v-if="notice"
        :role="notice.tone === 'error' ? 'alert' : 'status'"
        class="flex flex-wrap items-center justify-between gap-3 rounded-2xl border p-4 text-sm shadow-sm backdrop-blur"
        :class="{
          'border-emerald-200 bg-emerald-50/90 text-emerald-900':
            notice.tone === 'success',
          'border-amber-200 bg-amber-50/90 text-amber-900':
            notice.tone === 'pending',
          'border-rose-200 bg-rose-50/90 text-rose-900':
            notice.tone === 'error',
        }"
      >
        <div class="flex items-center gap-2.5">
          <span class="flex size-6 shrink-0 items-center justify-center rounded-lg text-sm font-bold">
            <template v-if="notice.tone === 'success'">✓</template>
            <template v-else-if="notice.tone === 'pending'">⏱</template>
            <template v-else>⚠️</template>
          </span>
          <span class="font-medium leading-relaxed">{{ notice.text }}</span>
        </div>
        <button
          type="button"
          class="text-xs font-semibold uppercase tracking-wider underline underline-offset-4 hover:opacity-80"
          @click="notice = null"
        >
          Dismiss
        </button>
      </div>

      <!-- Loading State -->
      <div
        v-if="loading"
        class="flex flex-col items-center justify-center gap-3 py-16 text-sm text-slate-500"
        aria-live="polite"
      >
        <svg class="size-6 animate-spin text-[#bc1823]" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <span>Loading your customer experience portal…</span>
      </div>

      <!-- Error State -->
      <div
        v-else-if="errorMessage"
        class="rounded-2xl border border-rose-200 bg-rose-50/90 p-6 text-sm text-rose-900 shadow-sm"
        role="alert"
      >
        <div class="flex items-start gap-3">
          <span class="text-xl">⚠️</span>
          <div>
            <h3 class="font-semibold text-base">Unable to load portal context</h3>
            <p class="mt-1 text-slate-700">{{ errorMessage }}</p>
          </div>
        </div>
      </div>

      <!-- Main Portal Navigation Tabs & Content -->
      <div v-else class="space-y-6">
        <!-- Segmented Tab Navigation Bar -->
        <nav
          class="flex items-center gap-2 overflow-x-auto border-b border-slate-200 pb-2 scrollbar-none"
          aria-label="Portal tabs"
        >
          <button
            type="button"
            class="flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs sm:text-sm font-semibold transition whitespace-nowrap"
            :class="
              activeTab === 'facilities'
                ? 'bg-slate-900 text-white shadow-sm'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
            "
            @click="activeTab = 'facilities'"
          >
            <span>🏥</span>
            <span>Facilities & Deals</span>
            <span
              class="rounded-full px-2 py-0.5 text-[11px] font-bold"
              :class="activeTab === 'facilities' ? 'bg-white/20 text-white' : 'bg-slate-200 text-slate-700'"
            >
              {{ facilityCount }}
            </span>
          </button>

          <button
            type="button"
            class="flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs sm:text-sm font-semibold transition whitespace-nowrap"
            :class="
              activeTab === 'renewal'
                ? 'bg-slate-900 text-white shadow-sm'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
            "
            @click="activeTab = 'renewal'"
          >
            <span>🪙</span>
            <span>Token Renewal & Plans</span>
          </button>

          <button
            type="button"
            class="flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs sm:text-sm font-semibold transition whitespace-nowrap"
            :class="
              activeTab === 'billing'
                ? 'bg-slate-900 text-white shadow-sm'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
            "
            @click="activeTab = 'billing'"
          >
            <span>💳</span>
            <span>Billing & Invoices</span>
            <span
              v-if="openInvoiceCount > 0"
              class="rounded-full px-2 py-0.5 text-[11px] font-bold bg-amber-500 text-white"
            >
              {{ openInvoiceCount }}
            </span>
          </button>

          <button
            type="button"
            class="flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs sm:text-sm font-semibold transition whitespace-nowrap"
            :class="
              activeTab === 'support'
                ? 'bg-slate-900 text-white shadow-sm'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
            "
            @click="activeTab = 'support'"
          >
            <span>💬</span>
            <span>Communications & Support</span>
          </button>
        </nav>

        <!-- TAB 1: Facilities & Deals -->
        <section v-if="activeTab === 'facilities'" class="space-y-6">
          <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <h2 class="text-xl font-bold tracking-tight text-slate-900">
                Connected Facilities & Plans
              </h2>
              <p class="text-xs text-slate-500 mt-0.5">
                Each facility is configured with an active digital plan, token allocation, and Go-Live verification status.
              </p>
            </div>
            <span class="text-xs font-semibold text-slate-500">
              {{ allFacilities.length }} Active Clinic{{ allFacilities.length > 1 ? 's' : '' }}
            </span>
          </div>

          <!-- Empty State -->
          <div
            v-if="!allFacilities.length"
            class="rounded-2xl border border-slate-200 bg-white p-8 text-center"
          >
            <span class="text-3xl">🏥</span>
            <h3 class="mt-3 text-base font-semibold text-slate-900">No facilities linked</h3>
            <p class="mt-1 text-xs text-slate-500 max-w-md mx-auto">
              We did not find any registered facilities linked to your account yet. If you recently onboarded, verification may take a few moments.
            </p>
          </div>

          <!-- Facility Cards Grid -->
          <div v-else class="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            <article
              v-for="facility in allFacilities"
              :key="facility.mfl_code"
              class="flex flex-col justify-between rounded-2xl border border-slate-200 bg-white p-6 shadow-sm transition hover:border-[#bc1823]/40 hover:shadow-md"
            >
              <div>
                <!-- Top Badge Row -->
                <div class="flex items-start justify-between gap-3">
                  <div class="space-y-1">
                    <span
                      v-if="facility.keph_level"
                      class="inline-flex items-center rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-700 border border-slate-200"
                    >
                      {{ facility.keph_level }}
                    </span>
                    <span
                      v-else
                      class="inline-flex items-center rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-700 border border-slate-200"
                    >
                      Clinic
                    </span>
                    <h3 class="text-lg font-bold text-slate-900 leading-snug">
                      {{ facility.facility_name }}
                    </h3>
                  </div>

                  <span
                    class="shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-semibold border flex items-center gap-1.5"
                    :class="
                      facility.go_live
                        ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                        : 'bg-amber-50 text-amber-800 border-amber-200'
                    "
                  >
                    <span
                      class="size-1.5 rounded-full"
                      :class="facility.go_live ? 'bg-emerald-600' : 'bg-amber-600'"
                    ></span>
                    <span>{{ facility.go_live ? 'Live' : 'In Verification' }}</span>
                  </span>
                </div>

                <!-- MFL & Deal Info Ribbon -->
                <div class="mt-4 flex flex-wrap items-center gap-2 text-xs">
                  <button
                    type="button"
                    class="inline-flex items-center gap-1.5 rounded-lg bg-slate-100 px-2.5 py-1 font-mono font-medium text-slate-700 hover:bg-slate-200 transition border border-slate-200/80"
                    title="Click to copy MFL Code"
                    @click="copyMfl(facility.mfl_code)"
                  >
                    <span>MFL: {{ facility.mfl_code }}</span>
                    <span class="text-[10px]">{{ copiedMfl === facility.mfl_code ? '✓ Copied' : '📋' }}</span>
                  </button>

                  <span
                    v-if="facility.deal"
                    class="inline-flex items-center gap-1 rounded-lg bg-red-50 border border-red-200 px-2.5 py-1 text-slate-700 font-medium"
                  >
                    <span>Deal:</span>
                    <strong class="text-[#bc1823]">#{{ facility.deal }}</strong>
                  </span>
                </div>

                <!-- Subscription & Token Status Box -->
                <div class="mt-4 rounded-xl border border-slate-100 bg-slate-50/80 p-3.5 space-y-2 text-xs">
                  <div class="flex items-center justify-between">
                    <span class="text-slate-500 font-medium">Active Package</span>
                    <span class="font-semibold text-slate-900 truncate max-w-[180px]">
                      {{ facility.token_package || 'No Active Package' }}
                    </span>
                  </div>

                  <div class="flex items-center justify-between">
                    <span class="text-slate-500 font-medium">Token Allocation</span>
                    <span class="inline-flex items-center gap-1 font-bold text-[#bc1823]">
                      <span>🪙</span>
                      <span>{{ (facility.token_quantity || 0).toLocaleString() }} Tokens</span>
                    </span>
                  </div>

                  <div v-if="facility.package_gross_total != null" class="flex items-center justify-between border-t border-slate-200/60 pt-2">
                    <span class="text-slate-500 font-medium">Plan Value</span>
                    <span class="font-semibold text-slate-900">
                      {{ Number(facility.package_gross_total) === 0 ? 'Free Trial' : money(facility.package_gross_total, facility.package_currency) }}
                      <span v-if="Number(facility.package_gross_total) > 0" class="text-[10px] font-normal text-slate-500">incl. VAT</span>
                    </span>
                  </div>
                </div>
              </div>

              <!-- Card Action CTAs -->
              <div class="mt-5 pt-4 border-t border-slate-100 flex items-center gap-2">
                <button
                  type="button"
                  class="flex-1 inline-flex items-center justify-center gap-1.5 rounded-xl bg-[#bc1823] px-3.5 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-[#a3141d]"
                  @click="selectFacilityForRenewal(facility)"
                >
                  <span>Renew / Top-Up</span>
                  <span>→</span>
                </button>

                <button
                  type="button"
                  class="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50"
                  title="Simulate volume in Sizing Calculator"
                  @click="openCalculatorForFacility(facility)"
                >
                  <span>🧮</span>
                </button>
              </div>
            </article>
          </div>
        </section>

        <!-- TAB 2: Token Renewal & Packages -->
        <section v-if="activeTab === 'renewal'" class="space-y-6">
          <div class="rounded-2xl border border-slate-200 bg-white p-6 sm:p-8 shadow-sm space-y-6">
            <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
              <div>
                <span class="inline-flex items-center gap-1.5 rounded-full border border-red-200 bg-red-50 px-3 py-0.5 text-xs font-semibold uppercase tracking-wider text-[#bc1823]">
                  Token Renewal & Capacity
                </span>
                <h2 class="mt-2 text-xl sm:text-2xl font-bold tracking-tight text-slate-900">
                  Select Facility & Token Tier
                </h2>
                <p class="text-xs sm:text-sm text-slate-600 mt-1">
                  Care tokens power clinical registrations, consultations, laboratory orders, and claim processing.
                </p>
              </div>

              <!-- Target Facility Selector -->
              <div class="min-w-[280px]">
                <label class="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
                  Target Facility for Order
                </label>
                <select
                  v-model="selectedFacilityMfl"
                  class="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-xs sm:text-sm font-semibold text-slate-900 shadow-sm transition focus:border-[#bc1823] focus:outline-none focus:ring-4 focus:ring-[#bc1823]/10"
                >
                  <option
                    v-for="fac in allFacilities"
                    :key="fac.mfl_code"
                    :value="fac.mfl_code"
                  >
                    {{ fac.facility_name }} (MFL: {{ fac.mfl_code }})
                  </option>
                </select>
              </div>
            </div>

            <!-- Target Facility Info Banner -->
            <div
              v-if="selectedFacility"
              class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-100 bg-slate-50 p-4 text-xs"
            >
              <div class="flex items-center gap-2.5">
                <span class="text-base">🏥</span>
                <div>
                  <span class="font-bold text-slate-900">{{ selectedFacility.facility_name }}</span>
                  <span class="text-slate-500"> · MFL: {{ selectedFacility.mfl_code }}</span>
                </div>
              </div>

              <div class="flex items-center gap-3">
                <span class="text-slate-600">
                  Current plan: <strong>{{ selectedFacility.token_package || 'None' }}</strong>
                </span>
                <span class="inline-flex items-center gap-1 rounded bg-red-50 border border-red-200 px-2 py-0.5 font-bold text-[#bc1823]">
                  <span>🪙</span>
                  <span>{{ (selectedFacility.token_quantity || 0).toLocaleString() }} tokens</span>
                </span>
              </div>
            </div>

            <!-- Sizing Calculator Callout Banner -->
            <div
              class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 rounded-xl border border-slate-200 bg-gradient-to-r from-red-50/50 via-white to-slate-50 p-4 shadow-sm"
            >
              <div class="flex items-center gap-3.5">
                <div
                  class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-[#bc1823] text-white text-lg shadow-sm"
                >
                  🧮
                </div>
                <div>
                  <h4 class="text-xs sm:text-sm font-bold text-slate-900">
                    Not sure how many tokens {{ selectedFacility?.facility_name || 'your clinic' }} needs?
                  </h4>
                  <p class="text-xs text-slate-500 mt-0.5">
                    Use the CareVerse Token Sizing Calculator to model daily patient visits, labs, prescriptions, and expected revenue.
                  </p>
                </div>
              </div>
              <button
                type="button"
                class="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-white border border-slate-300 px-4 py-2 text-xs font-semibold text-slate-800 shadow-sm transition hover:border-[#bc1823] hover:text-[#bc1823] hover:bg-red-50/50"
                @click="portalCalculatorDialogOpen = true"
              >
                <span>Launch Sizing Calculator</span>
                <span>→</span>
              </button>
            </div>

            <!-- Available Token Packages Grid -->
            <div class="space-y-4">
              <div class="flex items-center justify-between">
                <h3 class="text-sm font-bold uppercase tracking-wider text-slate-700">
                  Available Care Packages
                </h3>
                <span class="text-xs text-slate-500">VAT calculated transparently</span>
              </div>

              <div class="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
                <article
                  v-for="item in context.token_packages"
                  :key="item.item_code"
                  class="rounded-2xl border bg-white p-5 shadow-sm transition hover:border-[#bc1823]/50 hover:shadow-md flex flex-col justify-between cursor-pointer"
                  :class="
                    selectedPortalPackageCode === item.item_code
                      ? 'border-2 border-[#bc1823] bg-red-50/20 ring-4 ring-[#bc1823]/10 shadow-md'
                      : 'border-slate-200'
                  "
                  @click="selectedPortalPackageCode = item.item_code"
                >
                  <div>
                    <div class="flex items-center justify-between">
                      <h4 class="text-base font-bold text-slate-900">
                        {{ item.display_name || item.item_code }}
                      </h4>
                      <span
                        v-if="Number(item.price_ex_vat ?? item.price ?? 0) === 0"
                        class="rounded-full bg-slate-100 border border-slate-200 px-2 py-0.5 text-[10px] font-bold text-slate-700"
                      >
                        Free Trial
                      </span>
                    </div>

                    <p class="mt-3 text-2xl font-extrabold text-slate-900 tracking-tight">
                      {{ Number(item.price_ex_vat ?? item.price ?? 0) === 0 ? 'KES 0' : money(item.price_ex_vat ?? item.price, item.currency) }}
                      <span class="text-xs font-normal text-slate-500">
                        {{ Number(item.price_ex_vat ?? item.price ?? 0) === 0 ? 'Zero commitment' : 'excl. VAT' }}
                      </span>
                    </p>

                    <p v-if="Number(item.gross_total) > 0" class="mt-1 text-xs text-slate-500">
                      {{ item.vat_label || 'VAT (16%)' }}
                      {{ money(item.vat_amount, item.currency) }} · Total
                      <strong class="text-slate-800">{{ money(item.gross_total, item.currency) }}</strong>
                    </p>

                    <div class="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-red-50 border border-red-200/60 px-2.5 py-1 text-xs font-bold text-[#bc1823]">
                      <span>🪙</span>
                      <span>{{ (item.token_quantity || 100).toLocaleString() }} Care Tokens</span>
                    </div>

                    <p class="mt-3 text-xs leading-relaxed text-slate-600">
                      {{ item.coverage_summary || item.description }}
                    </p>
                  </div>

                  <!-- Purchase Button -->
                  <div class="mt-5 pt-4 border-t border-slate-100">
                    <button
                      type="button"
                      class="flex min-h-11 w-full items-center justify-center gap-1.5 rounded-xl bg-[#bc1823] px-4 py-2.5 text-xs font-semibold text-white shadow-sm transition hover:bg-[#a3141d] disabled:opacity-50"
                      :disabled="purchaseBusy"
                      @click.stop="buyPackage(item)"
                    >
                      <template v-if="purchaseBusy">
                        <svg class="size-4 animate-spin text-white" fill="none" viewBox="0 0 24 24">
                          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        <span>Processing…</span>
                      </template>
                      <template v-else-if="existingOrderForSelectedFacility(item)">
                        <span>Order Active ({{ existingOrderForSelectedFacility(item).name }})</span>
                      </template>
                      <template v-else-if="Number(item.price_ex_vat ?? item.price ?? 0) === 0">
                        <span>Activate Free Trial</span>
                      </template>
                      <template v-else>
                        <span>Order for {{ selectedFacility?.facility_name ? selectedFacility.facility_name.split(' ')[0] : 'Facility' }}</span>
                      </template>
                    </button>
                  </div>
                </article>
              </div>
            </div>
          </div>
        </section>

        <!-- TAB 3: Billing & Invoices -->
        <section v-if="activeTab === 'billing'" class="space-y-6">
          <div class="grid gap-6 lg:grid-cols-2">
            <!-- Open Invoices Column -->
            <div class="space-y-4">
              <div class="flex items-center justify-between">
                <div>
                  <h3 class="text-base font-bold text-slate-900">
                    Open Invoices
                  </h3>
                  <p class="text-xs text-slate-500">
                    Settle invoices instantly via M-Pesa or Card checkout.
                  </p>
                </div>
                <span
                  class="rounded-full px-2.5 py-0.5 text-xs font-bold"
                  :class="allInvoices.length ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'"
                >
                  {{ allInvoices.length }} Open
                </span>
              </div>

              <!-- No Invoices Empty State -->
              <div
                v-if="!allInvoices.length"
                class="rounded-2xl border border-slate-200 bg-white p-8 text-center"
              >
                <span class="text-3xl">🎉</span>
                <h4 class="mt-3 text-sm font-semibold text-slate-900">All invoices settled</h4>
                <p class="mt-1 text-xs text-slate-500">
                  There are no outstanding invoices for your linked accounts at this time.
                </p>
              </div>

              <!-- Invoices List -->
              <div v-else class="space-y-3">
                <article
                  v-for="invoice in allInvoices"
                  :key="invoice.name"
                  class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-slate-300 flex flex-col justify-between gap-4"
                >
                  <div class="flex items-start justify-between gap-3">
                    <div>
                      <div class="flex items-center gap-2">
                        <h4 class="font-bold text-sm text-slate-900">
                          {{ invoice.invoice_number || invoice.name }}
                        </h4>
                        <span
                          class="rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider"
                          :class="
                            invoiceStatus(invoice).key === 'overdue'
                              ? 'bg-rose-100 text-rose-800'
                              : 'bg-amber-100 text-amber-800'
                          "
                        >
                          {{ invoiceStatus(invoice).label }}
                        </span>
                      </div>
                      <p class="mt-1 text-xs text-slate-500">
                        Due: <strong>{{ invoice.due_date || 'On Receipt' }}</strong>
                        <span v-if="invoice.posting_date"> · Issued: {{ invoice.posting_date }}</span>
                      </p>
                    </div>

                    <div class="text-right">
                      <p class="text-lg font-bold text-slate-900">
                        {{ money(invoice.amount, invoice.currency) }}
                      </p>
                      <span class="text-[10px] text-slate-500 uppercase tracking-wider">Amount Due</span>
                    </div>
                  </div>

                  <div class="flex items-center justify-between border-t border-slate-100 pt-3">
                    <span class="text-[11px] text-slate-500">
                      Payment powered by Paystack (M-Pesa & Card)
                    </span>

                    <button
                      type="button"
                      class="inline-flex min-h-10 items-center gap-1.5 rounded-xl bg-[#bc1823] px-4 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-[#a3141d] disabled:opacity-50"
                      :disabled="busyId === invoice.name"
                      @click="payInvoice(invoice)"
                    >
                      <template v-if="busyId === invoice.name">
                        <svg class="size-3.5 animate-spin text-white" fill="none" viewBox="0 0 24 24">
                          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        <span>Opening Checkout…</span>
                      </template>
                      <template v-else>
                        <span>Pay via M-Pesa / Card</span>
                        <span>→</span>
                      </template>
                    </button>
                  </div>
                </article>
              </div>
            </div>

            <!-- Active Token Orders Column -->
            <div class="space-y-4">
              <div class="flex items-center justify-between">
                <div>
                  <h3 class="text-base font-bold text-slate-900">
                    Token Orders
                  </h3>
                  <p class="text-xs text-slate-500">
                    Created orders awaiting invoice generation.
                  </p>
                </div>
                <span class="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-bold text-slate-700">
                  {{ allOrders.length }} Orders
                </span>
              </div>

              <!-- No Orders Empty State -->
              <div
                v-if="!allOrders.length"
                class="rounded-2xl border border-slate-200 bg-white p-8 text-center"
              >
                <span class="text-3xl">📦</span>
                <h4 class="mt-3 text-sm font-semibold text-slate-900">No active orders</h4>
                <p class="mt-1 text-xs text-slate-500">
                  You have no pending orders. Select a package under Token Renewal to generate capacity.
                </p>
              </div>

              <!-- Orders List -->
              <div v-else class="space-y-3">
                <article
                  v-for="order in allOrders"
                  :key="order.name"
                  class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-slate-300 flex flex-col justify-between gap-4"
                >
                  <div class="flex items-start justify-between gap-3">
                    <div>
                      <div class="flex items-center gap-2">
                        <h4 class="font-bold text-sm text-slate-900">
                          {{ packageLabel(order.crm_token_package_item, context.token_packages) }}
                        </h4>
                        <span class="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-700">
                          {{ order.name }}
                        </span>
                      </div>
                      <p class="mt-1 text-xs text-slate-500">
                        Facility: <strong>{{ facilityLabel(order.crm_token_facility_mfl, allFacilities) }}</strong>
                        <span v-if="order.transaction_date"> · Ordered: {{ order.transaction_date }}</span>
                      </p>
                    </div>

                    <div class="text-right">
                      <p class="text-base font-bold text-slate-900">
                        {{ money(order.grand_total, order.currency) }}
                      </p>
                      <span class="text-[10px] text-slate-500">incl. VAT</span>
                    </div>
                  </div>

                  <div class="flex items-center justify-between border-t border-slate-100 pt-3">
                    <p v-if="!order.can_create_invoice" class="text-xs text-slate-500 italic">
                      {{ invoiceUnavailableMessage(order) }}
                    </p>
                    <p v-else class="text-xs text-slate-500">
                      Ready to invoice
                    </p>

                    <button
                      v-if="order.can_create_invoice"
                      type="button"
                      class="inline-flex min-h-10 items-center gap-1.5 rounded-xl bg-slate-900 px-4 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-black disabled:opacity-50"
                      :disabled="busyId === order.name"
                      @click="createInvoice(order)"
                    >
                      <template v-if="busyId === order.name">
                        <svg class="size-3.5 animate-spin text-white" fill="none" viewBox="0 0 24 24">
                          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        <span>Generating Invoice…</span>
                      </template>
                      <template v-else>
                        <span>Generate Invoice</span>
                        <span>→</span>
                      </template>
                    </button>
                  </div>
                </article>
              </div>
            </div>
          </div>

          <!-- Alternative Payment Information Card -->
          <div class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h4 class="text-sm font-bold text-slate-900">
              Direct Bank Settlement & M-Pesa Paybill
            </h4>
            <p class="mt-1 text-xs text-slate-500 leading-relaxed">
              If your finance team prefers settling invoices via bank wire or direct M-Pesa Paybill, please reference your Invoice Number on the transaction remark and notify our billing desk at <strong>finance@tiberbu.health</strong>.
            </p>
          </div>
        </section>

        <!-- TAB 4: Support & Communications -->
        <section v-if="activeTab === 'support'" class="space-y-6">
          <div class="grid gap-6 md:grid-cols-2">
            <!-- Dedicated Support Channels -->
            <div class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
              <span class="inline-flex items-center gap-1.5 rounded-full border border-red-200 bg-red-50 px-3 py-0.5 text-xs font-semibold uppercase tracking-wider text-[#bc1823]">
                Customer Support
              </span>
              <h3 class="text-lg font-bold text-slate-900">
                Direct Care & Clinical Support
              </h3>
              <p class="text-xs text-slate-600 leading-relaxed">
                Our clinical onboarding specialists and operations team are available 24/7 to assist with facility verification, care token allocation, and EMR integration.
              </p>

              <div class="space-y-3 pt-2">
                <div class="flex items-center gap-3 rounded-xl border border-slate-100 bg-slate-50 p-3.5 text-xs">
                  <span class="text-lg">✉️</span>
                  <div>
                    <span class="block font-semibold text-slate-900">Operations & Billing Helpdesk</span>
                    <a href="mailto:support@tiberbu.health" class="text-[#bc1823] font-semibold hover:underline">
                      support@tiberbu.health
                    </a>
                  </div>
                </div>

                <div class="flex items-center gap-3 rounded-xl border border-slate-100 bg-slate-50 p-3.5 text-xs">
                  <span class="text-lg">📞</span>
                  <div>
                    <span class="block font-semibold text-slate-900">Priority Telephone & WhatsApp Hotline</span>
                    <span class="font-mono text-slate-700 font-semibold">+254 700 000 000</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Network Partner Information -->
            <div class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
              <span class="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-100 px-3 py-0.5 text-xs font-semibold uppercase tracking-wider text-slate-700">
                Network Affiliation
              </span>
              <h3 class="text-lg font-bold text-slate-900">
                Partner Network & Standards
              </h3>
              <p class="text-xs text-slate-600 leading-relaxed">
                Your facilities operate under unified partner standards ensuring verified MFL registry compliance, synchronized health data, and insured clinical coverage.
              </p>

              <div class="rounded-xl border border-slate-100 bg-slate-50 p-4 space-y-2 text-xs">
                <div class="flex items-center justify-between">
                  <span class="text-slate-500 font-medium">Assigned Network</span>
                  <span class="font-bold text-slate-900">
                    {{ primaryCustomerAccount?.network || allFacilities[0]?.network || 'CareVerse Health Network' }}
                  </span>
                </div>
                <div class="flex items-center justify-between">
                  <span class="text-slate-500 font-medium">Registry Status</span>
                  <span class="inline-flex items-center gap-1 font-semibold text-emerald-700">
                    <span class="size-1.5 rounded-full bg-emerald-600"></span>
                    <span>Synchronized with KMHFR / MFL</span>
                  </span>
                </div>
                <div class="flex items-center justify-between">
                  <span class="text-slate-500 font-medium">Security & Compliance</span>
                  <span class="font-semibold text-slate-900">Data Protection Act (Kenya) Compliant</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Token Consumption Reference Table -->
          <div class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
            <h3 class="text-base font-bold text-slate-900">
              Care Token Consumption Rates
            </h3>
            <p class="text-xs text-slate-500">
              Tokens are deducted only upon successful execution of verified clinical milestones.
            </p>

            <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 pt-2">
              <div class="rounded-xl border border-slate-100 bg-slate-50 p-3.5 text-xs space-y-1">
                <span class="font-bold text-slate-900">Patient Registration</span>
                <p class="text-slate-500 text-[11px]">Intake & biometric/vitals capture</p>
                <span class="font-bold text-[#bc1823]">6 Tokens / event</span>
              </div>

              <div class="rounded-xl border border-slate-100 bg-slate-50 p-3.5 text-xs space-y-1">
                <span class="font-bold text-slate-900">Outpatient Consultation</span>
                <p class="text-slate-500 text-[11px]">Doctor encounter & diagnosis</p>
                <span class="font-bold text-[#bc1823]">3 Tokens / visit</span>
              </div>

              <div class="rounded-xl border border-slate-100 bg-slate-50 p-3.5 text-xs space-y-1">
                <span class="font-bold text-slate-900">Laboratory & Pharmacy</span>
                <p class="text-slate-500 text-[11px]">Diagnostics order & dispensing</p>
                <span class="font-bold text-[#bc1823]">6 Tokens / order</span>
              </div>

              <div class="rounded-xl border border-slate-100 bg-slate-50 p-3.5 text-xs space-y-1">
                <span class="font-bold text-slate-900">Imaging & Inpatient</span>
                <p class="text-slate-500 text-[11px]">X-Ray, Ultrasound & admission</p>
                <span class="font-bold text-[#bc1823]">12 Tokens / order</span>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>

    <!-- CareVerse Token Sizing Calculator Modal Dialog -->
    <Dialog
      v-model:open="portalCalculatorDialogOpen"
      :title="__('CareVerse Token Sizing Calculator')"
      size="4xl"
    >
      <div class="p-2 max-h-[80vh] overflow-y-auto">
        <TokenCalculator
          :packages="context.token_packages"
          :config="context.calculator_config"
          :selected-package-code="selectedPortalPackageCode"
          :facility-name="selectedFacility?.facility_name"
          context="portal"
          @select-package="onCalculatorSelectPackage"
          @apply-plan="onCalculatorApplyPlan"
        />
      </div>
    </Dialog>
  </main>
</template>
