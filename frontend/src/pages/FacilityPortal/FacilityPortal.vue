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

const activeTab = ref('facilities') // 'facilities' | 'billing' | 'support'
const selectedFacilityMfl = ref('')
const selectedTopUpPackageCode = ref('')
const topUpModalOpen = ref(false)
const calculatorModalOpen = ref(false)
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
          keph_level: fac.keph_level || 'Clinic',
          network: fac.network || account.network || 'CareVerse Partner Network',
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
          keph_level: fac.keph_level || 'Clinic',
          network: submission.network_slug || 'CareVerse Partner Network',
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

// Currently Selected Facility for Top-Up / Calculator
const selectedFacility = computed(() => {
  if (selectedFacilityMfl.value) {
    const found = allFacilities.value.find(
      (f) => String(f.mfl_code).toLowerCase() === String(selectedFacilityMfl.value).toLowerCase(),
    )
    if (found) return found
  }
  return allFacilities.value[0] || null
})

// Selected Package Object in Modal
const selectedPackageObj = computed(() => {
  return (
    context.value.token_packages?.find(
      (p) => p.item_code === selectedTopUpPackageCode.value,
    ) || context.value.token_packages?.[1] || null // Default to Starter
  )
})

// Summary KPI Computations
const facilityCount = computed(() => allFacilities.value.length)

const totalTokenCount = computed(() =>
  allFacilities.value.reduce((sum, fac) => sum + (fac.token_quantity || 0), 0),
)

// Estimated clinical encounters supported (average 15 tokens per full encounter: consult + vitals + lab/pharmacy)
const estimatedEncounters = computed(() => {
  const count = Math.floor(totalTokenCount.value / 15)
  return count > 0 ? count : 0
})

const liveFacilitiesCount = computed(
  () => allFacilities.value.filter((f) => f.go_live).length,
)

const pendingOrderCount = computed(
  () => allOrders.value.filter((order) => order.can_create_invoice).length,
)

const openInvoiceCount = computed(() => allInvoices.value.length)

const totalOutstandingAmount = computed(() =>
  allInvoices.value.reduce((sum, inv) => sum + (Number(inv.amount) || 0), 0),
)

const primaryOrganizationName = computed(() => {
  return (
    context.value.customer_accounts?.[0]?.organization ||
    context.value.customer_accounts?.[0]?.customer ||
    allFacilities.value[0]?.organization ||
    context.value.user ||
    'Health Facility'
  )
})

const primaryNetworkName = computed(() => {
  return (
    context.value.customer_accounts?.[0]?.network ||
    allFacilities.value[0]?.network ||
    'CareVerse Partner Network'
  )
})

const defaultCurrency = computed(() => {
  return (
    allInvoices.value[0]?.currency ||
    context.value.token_packages?.[0]?.currency ||
    'KES'
  )
})

// Actions & Navigation Helpers
function copyMfl(code) {
  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(code)
    copiedMfl.value = code
    setTimeout(() => {
      if (copiedMfl.value === code) copiedMfl.value = ''
    }, 2000)
  }
}

function openTopUpModal(facility = null) {
  if (facility) {
    selectedFacilityMfl.value = facility.mfl_code
  } else if (!selectedFacilityMfl.value && allFacilities.value.length) {
    selectedFacilityMfl.value = allFacilities.value[0].mfl_code
  }
  // Pick default package (Growth or Starter)
  if (!selectedTopUpPackageCode.value && context.value.token_packages?.length) {
    selectedTopUpPackageCode.value =
      context.value.token_packages.find((p) => p.item_code === 'CV-TOKEN-GROWTH')
        ?.item_code || context.value.token_packages[0].item_code
  }
  topUpModalOpen.value = true
}

function openCalculatorModal(facility = null) {
  if (facility) {
    selectedFacilityMfl.value = facility.mfl_code
  }
  calculatorModalOpen.value = true
}

function onCalculatorApplyPlan(pkg) {
  calculatorModalOpen.value = false
  selectedTopUpPackageCode.value = pkg.item_code
  openTopUpModal(selectedFacility.value)
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

async function executeTopUp() {
  if (!selectedFacility.value) {
    notice.value = {
      tone: 'error',
      text: 'Please select a facility to receive this token package.',
    }
    return
  }
  if (!selectedPackageObj.value) {
    notice.value = {
      tone: 'error',
      text: 'Please select a token package.',
    }
    return
  }

  purchaseBusy.value = true
  notice.value = null

  try {
    const params = {
      facility_mfl: selectedFacility.value.mfl_code,
      package_item_code: selectedPackageObj.value.item_code,
    }
    if (selectedFacility.value.customer) {
      params.customer = selectedFacility.value.customer
    } else if (selectedFacility.value.ois_name) {
      params.ois_number = selectedFacility.value.ois_name
    }

    const payload = unwrap(
      await call('crm.api.customer_experience.create_token_order', params),
    )

    topUpModalOpen.value = false
    notice.value = {
      tone: 'success',
      text: `Order ${payload.sales_order || ''} successfully created for ${selectedFacility.value.facility_name}. Review it below under Invoices & Billing to complete payment.`,
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
  <main class="min-h-screen bg-[#fafbfc] text-slate-800 antialiased selection:bg-red-100 selection:text-red-900">
    <!-- Top Utility Navigation -->
    <header class="border-b border-slate-200/80 bg-white sticky top-0 z-20">
      <div class="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
        <div class="flex items-center gap-3">
          <div class="flex size-8 items-center justify-center rounded-lg bg-[#bc1823] text-white font-bold text-sm shadow-sm">
            T
          </div>
          <div>
            <span class="text-sm font-bold text-slate-900 tracking-tight">Tiberbu</span>
            <span class="ml-1.5 text-xs font-medium text-slate-500">Customer Portal</span>
          </div>
        </div>

        <div class="flex items-center gap-4 text-xs">
          <span v-if="context.user" class="text-slate-600 hidden sm:inline-block font-medium">
            {{ context.user }}
          </span>
          <a
            href="/api/method/logout"
            class="rounded-lg border border-slate-200 px-3 py-1.5 font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-900 transition"
          >
            Sign out
          </a>
        </div>
      </div>
    </header>

    <div class="mx-auto max-w-6xl px-4 py-6 sm:px-6 space-y-6">
      <!-- Loading State -->
      <div v-if="loading" class="flex flex-col items-center justify-center py-20 text-slate-500 space-y-3" aria-live="polite">
        <svg class="size-6 animate-spin text-[#bc1823]" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <span class="text-xs font-medium">Opening your clinic portal…</span>
      </div>

      <!-- Error State -->
      <div v-else-if="errorMessage" class="rounded-xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-900" role="alert">
        <p class="font-semibold">Unable to load portal</p>
        <p class="text-xs mt-1 text-rose-700">{{ errorMessage }}</p>
      </div>

      <template v-else>
        <!-- Notice Alert (if any) -->
        <div
          v-if="notice"
          class="flex items-center justify-between rounded-xl border p-4 text-xs font-medium"
          :class="{
            'border-emerald-200 bg-emerald-50 text-emerald-900': notice.tone === 'success',
            'border-amber-200 bg-amber-50 text-amber-900': notice.tone === 'pending',
            'border-rose-200 bg-rose-50 text-rose-900': notice.tone === 'error',
          }"
        >
          <div class="flex items-center gap-2">
            <span>{{ notice.tone === 'success' ? '✓' : notice.tone === 'pending' ? '⏱' : '⚠️' }}</span>
            <span>{{ notice.text }}</span>
          </div>
          <button type="button" class="underline hover:opacity-80 ml-3 shrink-0" @click="notice = null">
            Dismiss
          </button>
        </div>

        <!-- LEVEL 0: Organization Context Header -->
        <section class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <div class="flex items-center gap-2">
              <span class="inline-block size-2 rounded-full bg-emerald-500"></span>
              <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">
                {{ primaryNetworkName }}
              </span>
            </div>
            <h1 class="text-2xl font-bold tracking-tight text-slate-900 mt-1">
              {{ primaryOrganizationName }}
            </h1>
          </div>

          <!-- Primary Header Action -->
          <div class="flex items-center gap-2.5">
            <button
              type="button"
              class="inline-flex items-center gap-1.5 rounded-xl bg-[#bc1823] px-4 py-2.5 text-xs font-bold text-white shadow-sm transition hover:bg-[#a3141d]"
              @click="openTopUpModal()"
            >
              <span>+</span>
              <span>Top Up Tokens</span>
            </button>
          </div>
        </section>

        <!-- LEVEL 1: HERO STATUS STRIP (The 3-Second Rule) -->
        <section class="grid gap-4 sm:grid-cols-3" aria-label="Facility status overview">
          <!-- Card 1: Token Capacity & Runway -->
          <div class="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-xs flex flex-col justify-between">
            <div>
              <span class="text-[11px] font-bold uppercase tracking-wider text-slate-500 block">
                Care Token Runway
              </span>
              <div class="mt-2 flex items-baseline gap-2">
                <span class="text-3xl font-extrabold text-slate-900 tracking-tight leading-none">
                  {{ totalTokenCount.toLocaleString() }}
                </span>
                <span class="text-xs font-semibold text-slate-500">Tokens</span>
              </div>
              <p class="mt-1.5 text-xs text-slate-500 leading-normal">
                Supports approx. <strong>~{{ estimatedEncounters }} patient visits</strong> across your clinics.
              </p>
            </div>
            <div class="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">
              <button
                type="button"
                class="text-xs font-bold text-[#bc1823] hover:underline"
                @click="openTopUpModal()"
              >
                + Top up balance →
              </button>
              <button
                type="button"
                class="text-[11px] font-medium text-slate-400 hover:text-slate-600"
                @click="openCalculatorModal()"
              >
                Sizing calculator
              </button>
            </div>
          </div>

          <!-- Card 2: Operational Live Status -->
          <div class="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-xs flex flex-col justify-between">
            <div>
              <span class="text-[11px] font-bold uppercase tracking-wider text-slate-500 block">
                Clinic Operations
              </span>
              <div class="mt-2 flex items-baseline gap-2">
                <span class="text-3xl font-extrabold text-slate-900 tracking-tight leading-none">
                  {{ facilityCount }}
                </span>
                <span class="text-xs font-semibold text-slate-500">
                  {{ facilityCount === 1 ? 'Clinic' : 'Clinics' }} Registered
                </span>
              </div>
              <p class="mt-1.5 text-xs text-slate-500 leading-normal">
                <span class="inline-block size-1.5 rounded-full bg-emerald-500 mr-1"></span>
                <strong>{{ liveFacilitiesCount }} Live</strong> on KMHFR Registry & Partner Network.
              </p>
            </div>
            <div class="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">
              <span class="text-xs font-medium text-slate-500">
                {{ liveFacilitiesCount === facilityCount ? 'All clinics ready' : 'Verification pending' }}
              </span>
              <button
                type="button"
                class="text-xs font-medium text-slate-600 hover:underline"
                @click="activeTab = 'facilities'"
              >
                View clinics →
              </button>
            </div>
          </div>

          <!-- Card 3: Invoices & Payment Action -->
          <div
            class="rounded-2xl border p-5 shadow-xs flex flex-col justify-between"
            :class="openInvoiceCount > 0 ? 'border-amber-200 bg-amber-50/40' : 'border-slate-200/90 bg-white'"
          >
            <div>
              <div class="flex items-center justify-between">
                <span class="text-[11px] font-bold uppercase tracking-wider text-slate-500 block">
                  Billing & Settlement
                </span>
                <span
                  v-if="openInvoiceCount > 0"
                  class="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-800"
                >
                  Action Required
                </span>
              </div>
              <div class="mt-2 flex items-baseline gap-2">
                <span
                  class="text-3xl font-extrabold tracking-tight leading-none"
                  :class="openInvoiceCount > 0 ? 'text-amber-900' : 'text-slate-900'"
                >
                  {{ openInvoiceCount > 0 ? money(totalOutstandingAmount) : 'Paid' }}
                </span>
                <span v-if="openInvoiceCount > 0" class="text-xs font-semibold text-amber-700">Due</span>
              </div>
              <p class="mt-1.5 text-xs text-slate-500 leading-normal">
                {{ openInvoiceCount > 0 ? `${openInvoiceCount} invoice awaiting settlement` : 'All invoices are up to date' }}
              </p>
            </div>
            <div class="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">
              <button
                v-if="openInvoiceCount > 0"
                type="button"
                class="text-xs font-bold text-amber-800 hover:underline"
                @click="activeTab = 'billing'"
              >
                Pay via M-Pesa / Card →
              </button>
              <button
                v-else
                type="button"
                class="text-xs font-medium text-slate-600 hover:underline"
                @click="activeTab = 'billing'"
              >
                Billing history →
              </button>
            </div>
          </div>
        </section>

        <!-- LEVEL 2: FOCUSED SECTION TABS -->
        <nav class="flex items-center gap-1 border-b border-slate-200 pt-2" aria-label="Portal sections">
          <button
            type="button"
            class="flex items-center gap-2 border-b-2 px-4 py-2.5 text-xs font-bold transition whitespace-nowrap"
            :class="
              activeTab === 'facilities'
                ? 'border-[#bc1823] text-[#bc1823]'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            "
            @click="activeTab = 'facilities'"
          >
            <span>My Facilities</span>
            <span class="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-600">
              {{ facilityCount }}
            </span>
          </button>

          <button
            type="button"
            class="flex items-center gap-2 border-b-2 px-4 py-2.5 text-xs font-bold transition whitespace-nowrap"
            :class="
              activeTab === 'billing'
                ? 'border-[#bc1823] text-[#bc1823]'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            "
            @click="activeTab = 'billing'"
          >
            <span>Invoices & Billing</span>
            <span
              v-if="openInvoiceCount > 0"
              class="rounded-full bg-amber-500 text-white px-2 py-0.5 text-[10px]"
            >
              {{ openInvoiceCount }}
            </span>
          </button>

          <button
            type="button"
            class="flex items-center gap-2 border-b-2 px-4 py-2.5 text-xs font-bold transition whitespace-nowrap"
            :class="
              activeTab === 'support'
                ? 'border-[#bc1823] text-[#bc1823]'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            "
            @click="activeTab = 'support'"
          >
            <span>Network Support</span>
          </button>
        </nav>

        <!-- VIEW 1: MY FACILITIES -->
        <section v-if="activeTab === 'facilities'" class="space-y-4">
          <div class="flex items-center justify-between">
            <h2 class="text-sm font-bold uppercase tracking-wider text-slate-600">
              Linked Clinic Facilities
            </h2>
            <span class="text-xs text-slate-500">
              Select any facility to top up tokens or simulate volume.
            </span>
          </div>

          <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            <article
              v-for="facility in allFacilities"
              :key="facility.mfl_code"
              class="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-xs flex flex-col justify-between hover:border-slate-300 transition"
            >
              <div>
                <!-- Top Row: Name & Live Status -->
                <div class="flex items-start justify-between gap-2">
                  <div>
                    <h3 class="text-base font-bold text-slate-900 leading-snug">
                      {{ facility.facility_name }}
                    </h3>
                    <div class="mt-1 flex items-center gap-2 text-xs text-slate-500">
                      <span>{{ facility.keph_level }}</span>
                      <span>·</span>
                      <button
                        type="button"
                        class="font-mono text-[11px] hover:text-slate-900 underline decoration-dotted"
                        title="Click to copy MFL Code"
                        @click="copyMfl(facility.mfl_code)"
                      >
                        {{ facility.mfl_code }}
                        <span v-if="copiedMfl === facility.mfl_code" class="text-emerald-600 font-bold ml-1">✓ Copied</span>
                      </button>
                    </div>
                  </div>

                  <span
                    class="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold border flex items-center gap-1"
                    :class="
                      facility.go_live
                        ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                        : 'bg-amber-50 text-amber-800 border-amber-200'
                    "
                  >
                    <span class="size-1.5 rounded-full" :class="facility.go_live ? 'bg-emerald-600' : 'bg-amber-600'"></span>
                    <span>{{ facility.go_live ? 'Live' : 'Verifying' }}</span>
                  </span>
                </div>

                <!-- Middle Box: Plan & Tokens -->
                <div class="mt-4 rounded-xl bg-slate-50 border border-slate-100 p-3 space-y-1.5 text-xs">
                  <div class="flex items-center justify-between text-slate-600">
                    <span class="font-medium">Active Plan</span>
                    <span class="font-semibold text-slate-900 truncate max-w-[170px]">
                      {{ facility.token_package || 'No Active Plan' }}
                    </span>
                  </div>
                  <div class="flex items-center justify-between text-slate-600">
                    <span class="font-medium">Tokens Active</span>
                    <span class="font-bold text-[#bc1823] inline-flex items-center gap-1">
                      <span>🪙</span>
                      <span>{{ (facility.token_quantity || 0).toLocaleString() }} Tokens</span>
                    </span>
                  </div>
                </div>
              </div>

              <!-- Action Footer -->
              <div class="mt-4 pt-3 border-t border-slate-100 flex items-center gap-2">
                <button
                  type="button"
                  class="flex-1 inline-flex items-center justify-center gap-1 rounded-xl bg-slate-900 px-3 py-2 text-xs font-bold text-white hover:bg-black transition shadow-xs"
                  @click="openTopUpModal(facility)"
                >
                  <span>+ Top Up Tokens</span>
                </button>
                <button
                  type="button"
                  class="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
                  title="Simulate volume with Sizing Calculator"
                  @click="openCalculatorModal(facility)"
                >
                  <span>🧮</span>
                </button>
              </div>
            </article>
          </div>
        </section>

        <!-- VIEW 2: INVOICES & BILLING -->
        <section v-if="activeTab === 'billing'" class="space-y-6">
          <div class="space-y-3">
            <h2 class="text-sm font-bold uppercase tracking-wider text-slate-600">
              Outstanding Invoices
            </h2>

            <div v-if="!allInvoices.length" class="rounded-2xl border border-slate-200 bg-white p-8 text-center text-xs text-slate-500">
              <span class="text-2xl block mb-2">🎉</span>
              <p class="font-bold text-slate-800 text-sm">No outstanding invoices</p>
              <p class="mt-0.5">All billing statements for your facilities have been settled.</p>
            </div>

            <div v-else class="space-y-3">
              <article
                v-for="invoice in allInvoices"
                :key="invoice.name"
                class="rounded-2xl border border-slate-200/90 bg-white p-4 sm:p-5 shadow-xs flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4"
              >
                <div class="space-y-1">
                  <div class="flex items-center gap-2">
                    <span class="font-bold text-sm text-slate-900">{{ invoice.invoice_number || invoice.name }}</span>
                    <span
                      class="rounded px-2 py-0.5 text-[10px] font-bold"
                      :class="invoiceStatus(invoice).key === 'overdue' ? 'bg-rose-100 text-rose-800' : 'bg-amber-100 text-amber-800'"
                    >
                      {{ invoiceStatus(invoice).label }}
                    </span>
                  </div>
                  <p class="text-xs text-slate-500">
                    Payment Due: <strong>{{ invoice.due_date || 'On Receipt' }}</strong>
                    <span v-if="invoice.posting_date"> · Issued: {{ invoice.posting_date }}</span>
                  </p>
                </div>

                <div class="flex items-center justify-between sm:justify-end gap-4 shrink-0">
                  <div class="text-right">
                    <span class="text-base font-extrabold text-slate-900 block leading-tight">
                      {{ money(invoice.amount, invoice.currency) }}
                    </span>
                    <span class="text-[10px] text-slate-400 uppercase font-medium">Balance</span>
                  </div>

                  <button
                    type="button"
                    class="inline-flex min-h-10 items-center gap-1.5 rounded-xl bg-[#bc1823] px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-[#a3141d] transition disabled:opacity-50"
                    :disabled="busyId === invoice.name"
                    @click="payInvoice(invoice)"
                  >
                    <span>{{ busyId === invoice.name ? 'Connecting…' : 'Pay via M-Pesa / Card →' }}</span>
                  </button>
                </div>
              </article>
            </div>
          </div>

          <!-- Pending Orders -->
          <div v-if="allOrders.length" class="space-y-3 pt-4 border-t border-slate-200">
            <h2 class="text-sm font-bold uppercase tracking-wider text-slate-600">
              Pending Orders Awaiting Invoice
            </h2>

            <div class="space-y-3">
              <article
                v-for="order in allOrders"
                :key="order.name"
                class="rounded-2xl border border-slate-200/90 bg-white p-4 shadow-xs flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3"
              >
                <div>
                  <span class="font-bold text-xs text-slate-900">
                    {{ packageLabel(order.crm_token_package_item, context.token_packages) }}
                  </span>
                  <span class="text-xs text-slate-500 ml-2">
                    For {{ facilityLabel(order.crm_token_facility_mfl, allFacilities) }} · Order #{{ order.name }}
                  </span>
                </div>

                <div class="flex items-center justify-between sm:justify-end gap-3">
                  <span class="text-xs font-bold text-slate-800">
                    {{ money(order.grand_total, order.currency) }} <span class="text-[10px] font-normal text-slate-400">incl. VAT</span>
                  </span>

                  <button
                    v-if="order.can_create_invoice"
                    type="button"
                    class="rounded-xl bg-slate-900 px-3 py-1.5 text-xs font-bold text-white hover:bg-black transition disabled:opacity-50"
                    :disabled="busyId === order.name"
                    @click="createInvoice(order)"
                  >
                    <span>{{ busyId === order.name ? 'Creating…' : 'Generate Invoice' }}</span>
                  </button>
                </div>
              </article>
            </div>
          </div>
        </section>

        <!-- VIEW 3: NETWORK SUPPORT -->
        <section v-if="activeTab === 'support'" class="space-y-4">
          <div class="rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs space-y-4 max-w-2xl">
            <div>
              <span class="text-xs font-bold uppercase tracking-wider text-[#bc1823] block">
                Dedicated Coordinator
              </span>
              <h2 class="text-lg font-bold text-slate-900 mt-1">
                Clinical Helpdesk & Partner Network Support
              </h2>
              <p class="text-xs text-slate-500 mt-1">
                Reach out directly for assistance with facility verification, token renewal, or clinical workflows.
              </p>
            </div>

            <div class="space-y-2.5 pt-2">
              <div class="rounded-xl bg-slate-50 border border-slate-100 p-3 text-xs flex items-center justify-between">
                <span class="text-slate-600 font-medium">Partner Network Lead</span>
                <span class="font-bold text-slate-900">{{ primaryNetworkName }}</span>
              </div>
              <div class="rounded-xl bg-slate-50 border border-slate-100 p-3 text-xs flex items-center justify-between">
                <span class="text-slate-600 font-medium">Email Desk</span>
                <a href="mailto:support@tiberbu.health" class="font-bold text-[#bc1823] hover:underline">
                  support@tiberbu.health
                </a>
              </div>
              <div class="rounded-xl bg-slate-50 border border-slate-100 p-3 text-xs flex items-center justify-between">
                <span class="text-slate-600 font-medium">Hotline & WhatsApp</span>
                <span class="font-bold text-slate-900 font-mono">+254 700 000 000</span>
              </div>
            </div>
          </div>

          <!-- Token Milestone Guide -->
          <div class="rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs space-y-3 max-w-2xl">
            <h3 class="text-sm font-bold text-slate-900">
              Care Token Consumption Rates
            </h3>
            <div class="grid grid-cols-2 gap-2 text-xs">
              <div class="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                <span class="font-bold text-slate-900 block">Consultation</span>
                <span class="text-slate-500 text-[11px]">3 Tokens per visit</span>
              </div>
              <div class="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                <span class="font-bold text-slate-900 block">Registration</span>
                <span class="text-slate-500 text-[11px]">6 Tokens per intake</span>
              </div>
              <div class="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                <span class="font-bold text-slate-900 block">Lab & Pharmacy</span>
                <span class="text-slate-500 text-[11px]">6 Tokens per order</span>
              </div>
              <div class="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                <span class="font-bold text-slate-900 block">Imaging & Admission</span>
                <span class="text-slate-500 text-[11px]">12 Tokens per order</span>
              </div>
            </div>
          </div>
        </section>
      </template>
    </div>

    <!-- MODAL 1: FOCUSED TOP-UP DIALOG -->
    <Dialog
      v-model:open="topUpModalOpen"
      :title="__('Top Up Care Tokens')"
      size="3xl"
    >
      <div class="p-1 space-y-5">
        <!-- Target Facility Picker -->
        <div>
          <label class="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1.5">
            Select Facility to Top Up
          </label>
          <select
            v-model="selectedFacilityMfl"
            class="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-xs sm:text-sm font-bold text-slate-900 shadow-xs focus:border-[#bc1823] focus:outline-none focus:ring-2 focus:ring-[#bc1823]/10"
          >
            <option
              v-for="fac in allFacilities"
              :key="fac.mfl_code"
              :value="fac.mfl_code"
            >
              {{ fac.facility_name }} (MFL: {{ fac.mfl_code }}) · Currently {{ fac.token_quantity || 0 }} tokens
            </option>
          </select>
        </div>

        <!-- Package Tier Selection Cards -->
        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <span class="text-xs font-bold uppercase tracking-wider text-slate-600">
              Select Token Package
            </span>
            <button
              type="button"
              class="text-xs font-bold text-[#bc1823] hover:underline"
              @click="topUpModalOpen = false; openCalculatorModal()"
            >
              Simulate in Calculator →
            </button>
          </div>

          <div class="grid gap-3 sm:grid-cols-2">
            <article
              v-for="pkg in context.token_packages"
              :key="pkg.item_code"
              class="rounded-xl border p-4 cursor-pointer transition flex flex-col justify-between"
              :class="
                selectedTopUpPackageCode === pkg.item_code
                  ? 'border-2 border-[#bc1823] bg-red-50/20 ring-2 ring-[#bc1823]/10 shadow-xs'
                  : 'border-slate-200 hover:border-slate-300 bg-white'
              "
              @click="selectedTopUpPackageCode = pkg.item_code"
            >
              <div>
                <div class="flex items-center justify-between">
                  <span class="font-bold text-sm text-slate-900">{{ pkg.display_name }}</span>
                  <span
                    v-if="Number(pkg.price_ex_vat ?? pkg.price ?? 0) === 0"
                    class="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold text-slate-600"
                  >
                    Free Trial
                  </span>
                  <span v-else class="font-bold text-xs text-[#bc1823]">
                    {{ money(pkg.gross_total || pkg.price, pkg.currency) }}
                  </span>
                </div>

                <div class="mt-2 text-xs text-slate-600">
                  <span class="font-bold text-slate-900">🪙 {{ (pkg.token_quantity || 0).toLocaleString() }} Tokens</span>
                </div>
                <p class="mt-1 text-[11px] text-slate-500 leading-normal">
                  {{ pkg.coverage_summary || pkg.description }}
                </p>
              </div>

              <div class="mt-3 pt-2 border-t border-slate-100 flex items-center justify-between text-[11px]">
                <span class="text-slate-400">
                  {{ Number(pkg.price_ex_vat ?? pkg.price ?? 0) === 0 ? 'No charge' : 'incl. 16% VAT' }}
                </span>
                <span
                  class="font-bold"
                  :class="selectedTopUpPackageCode === pkg.item_code ? 'text-[#bc1823]' : 'text-slate-400'"
                >
                  {{ selectedTopUpPackageCode === pkg.item_code ? 'Selected ✓' : 'Select' }}
                </span>
              </div>
            </article>
          </div>
        </div>

        <!-- Confirmation Action Footer -->
        <div class="pt-4 border-t border-slate-100 flex items-center justify-end gap-3">
          <button
            type="button"
            class="rounded-xl border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50"
            @click="topUpModalOpen = false"
          >
            Cancel
          </button>
          <button
            type="button"
            class="inline-flex items-center gap-1.5 rounded-xl bg-[#bc1823] px-5 py-2.5 text-xs font-bold text-white shadow-sm hover:bg-[#a3141d] disabled:opacity-50"
            :disabled="purchaseBusy || !selectedFacility || !selectedPackageObj"
            @click="executeTopUp()"
          >
            <span v-if="purchaseBusy">Processing Order…</span>
            <span v-else>Confirm & Order Tokens →</span>
          </button>
        </div>
      </div>
    </Dialog>

    <!-- MODAL 2: SIZING CALCULATOR DIALOG -->
    <Dialog
      v-model:open="calculatorModalOpen"
      :title="__('CareVerse Token Sizing Calculator')"
      size="4xl"
    >
      <div class="p-1 max-h-[80vh] overflow-y-auto">
        <TokenCalculator
          :packages="context.token_packages"
          :config="context.calculator_config"
          :selected-package-code="selectedTopUpPackageCode"
          :facility-name="selectedFacility?.facility_name"
          context="portal"
          @select-package="(code) => (selectedTopUpPackageCode = code)"
          @apply-plan="onCalculatorApplyPlan"
        />
      </div>
    </Dialog>
  </main>
</template>
