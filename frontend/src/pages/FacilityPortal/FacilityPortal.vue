<script setup>
import { computed, onMounted, ref } from 'vue'
import { call } from 'frappe-ui'
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

const loading = ref(true)
const errorMessage = ref('')
const context = ref({ user: '', ois: [], customer_accounts: [] })
const facilityCount = computed(() =>
  (context.value.customer_accounts || []).reduce(
    (total, account) => total + (account.facilities?.length || 0),
    (context.value.ois || []).reduce(
    (total, submission) =>
      total + (submission.progress?.facilities?.length || 0),
    0,
    ),
  ),
)
const invoiceReadyOrderCount = computed(() =>
  (context.value.ois || []).reduce(
    (total, submission) =>
      total +
      (submission.open_orders || []).filter((order) => order.can_create_invoice)
        .length,
    0,
  ),
)
const openInvoiceCount = computed(() =>
  (context.value.ois || []).reduce(
    (total, submission) => total + (submission.open_invoices?.length || 0),
    0,
  ),
)
const purchaseOis = ref('')
const purchaseFacility = ref('')
const purchaseBusy = ref(false)
const purchaseMessage = ref('')
const busyId = ref('')
const notice = ref(null)
const bankTransferOis = ref('')

function stepClass(step) {
  if (step.status === 'complete') return 'bg-emerald-600 text-white'
  if (step.status === 'current') return 'bg-[#bc1823] text-white'
  return 'bg-surface-gray-2 text-ink-gray-5'
}

function stepLabel(step) {
  if (step.status === 'complete') return 'Complete'
  if (step.status === 'current') return 'In progress'
  return 'Up next'
}

function customerStepLabel(step) {
  return step.label === 'GoLive' ? 'Service activation' : step.label
}

function invoiceUnavailableMessage(order) {
  const status = String(order.status || '').toLowerCase()
  if (status === 'on hold')
    return 'This order is on hold. Contact support if you need help.'
  if (status === 'closed' || status === 'cancelled')
    return 'This order is closed and cannot be invoiced.'
  return 'An invoice is not available for this order.'
}

function contractSummary(progress) {
  const contract = progress?.contract
  if (!contract?.required) return 'Contract is being prepared'
  return `${contract.signed} of ${contract.required} signatures complete`
}

function isSelfOnboarded(submission) {
  return submission?.onboarding_source === 'token_self_onboarding'
}

function money(value, currency) {
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: currency || 'KES',
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
}

async function createInvoice(orderName) {
  busyId.value = orderName
  notice.value = null
  try {
    await call('crm.api.customer_experience.start_token_payment', {
      sales_order: orderName,
    })
    await refreshContext()
    notice.value = {
      tone: 'success',
      text: 'Your invoice is ready. It will appear above so you can make payment when due.',
    }
  } catch {
    notice.value = {
      tone: 'error',
      text:
        'We could not create an invoice for this order. Please try again or contact support.',
    }
  } finally {
    busyId.value = ''
  }
}

async function payInvoice(oisName, invoice) {
  busyId.value = invoice.name
  notice.value = null
  bankTransferOis.value = ''
  try {
    const data = unwrap(
      await call('crm.api.checkout.initialize_portal_paystack_payment', {
        ois_number: oisName,
        invoice: invoice.name,
      }),
    )
    if (data.authorization_url) {
      window.location.href = data.authorization_url
      return
    }
    notice.value = { tone: 'error', text: 'Payment could not be started.' }
  } catch (error) {
    const failure = paymentFailureMessage(error)
    notice.value = { tone: 'error', text: failure.message }
    if (failure.offerBankTransfer) bankTransferOis.value = oisName
  } finally {
    busyId.value = ''
  }
}

async function verifyReturnedPayment() {
  const reference = referenceFromSearch(window.location.search)
  if (!reference) return
  const oisName = oisForReference(
    reference,
    (context.value.ois || []).map((item) => item.name),
  )
  window.history.replaceState({}, '', window.location.pathname)
  if (!oisName) return
  try {
    const result = unwrap(
      await call('crm.api.checkout.verify_portal_paystack_payment', {
        ois_number: oisName,
        reference,
      }),
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

function currentSubmission() {
  return context.value.ois?.find((item) => item.name === purchaseOis.value)
}

function purchaseFacilities() {
  return currentSubmission()?.progress?.facilities || []
}

function existingOrder(item) {
  return findOpenOrder(
    currentSubmission()?.open_orders,
    purchaseFacility.value,
    item.item_code,
  )
}

async function buyPackage(item) {
  purchaseMessage.value = ''
  if (!purchaseOis.value || !purchaseFacility.value) {
    purchaseMessage.value =
      'Select the facility that should receive this package.'
    return
  }
  purchaseBusy.value = true
  try {
    const payload = unwrap(
      await call('crm.api.customer_experience.create_token_order', {
        ois_number: purchaseOis.value,
        facility_mfl: purchaseFacility.value,
        package_item_code: item.item_code,
      }),
    )
    purchaseMessage.value = `Order ${payload.sales_order || ''} is ready${payload.idempotent ? ' (resumed)' : ''}. Review it under Token orders, then create its invoice when you're ready.`
    await refreshContext()
  } catch (error) {
    purchaseMessage.value =
      error?.messages?.[0] || 'We could not create the token order.'
  } finally {
    purchaseBusy.value = false
  }
}

onMounted(async () => {
  try {
    await refreshContext()
    purchaseOis.value = context.value.ois?.[0]?.name || ''
    purchaseFacility.value = purchaseFacilities()?.[0]?.mfl_code || ''
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
  <main class="min-h-screen bg-slate-50/70 text-slate-900 relative isolate selection:bg-red-100 selection:text-red-900">
    <div class="pointer-events-none fixed inset-0 -z-10 overflow-hidden" aria-hidden="true">
      <div class="absolute -top-40 right-1/4 h-96 w-96 rounded-full bg-red-400/10 blur-3xl"></div>
      <div class="absolute top-1/2 -left-24 h-96 w-96 rounded-full bg-emerald-400/10 blur-3xl"></div>
    </div>

    <header class="sticky top-0 z-30 border-b border-slate-200/80 bg-white/85 backdrop-blur-md">
      <div
        class="mx-auto flex max-w-6xl items-center justify-between px-5 py-3.5 sm:px-8"
      >
        <div class="flex items-center gap-3">
          <div
            class="flex size-9 items-center justify-center rounded-xl bg-gradient-to-br from-red-600 to-rose-700 text-white font-bold text-base shadow-sm shadow-red-600/30"
          >
            T
          </div>
          <div>
            <p class="text-sm font-bold tracking-tight text-slate-900">
              Tiberbu <span class="font-normal text-slate-500">Customer Experience</span>
            </p>
            <p class="text-[11px] font-medium text-slate-500 flex items-center gap-1.5">
              <span class="inline-block size-1.5 rounded-full bg-emerald-500"></span>
              Secure facility portal
            </p>
          </div>
        </div>
        <div class="flex items-center gap-3 text-xs sm:text-sm">
          <div
            v-if="context.user"
            class="hidden sm:inline-flex items-center gap-2 rounded-xl bg-slate-100/80 px-3 py-1.5 text-xs font-medium text-slate-700 border border-slate-200/60"
          >
            <span class="flex size-5 items-center justify-center rounded-full bg-slate-200 text-[10px] font-bold text-slate-600">
              👤
            </span>
            <span>{{ context.user }}</span>
          </div>
          <a
            class="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white/90 px-3.5 py-1.5 font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 hover:text-slate-900"
            href="/api/method/logout"
          >
            Sign out
          </a>
        </div>
      </div>
    </header>

    <div class="mx-auto max-w-6xl px-5 py-8 sm:px-8 sm:py-12">
      <!-- Hero Banner -->
      <section
        class="relative isolate overflow-hidden rounded-3xl border border-slate-200/80 bg-gradient-to-br from-red-50/70 via-white to-emerald-50/50 p-6 sm:p-9 shadow-[0_10px_30px_rgba(15,23,42,0.04)] backdrop-blur-md"
      >
        <div class="max-w-2xl">
          <span
            class="inline-flex items-center gap-1.5 rounded-full border border-red-200 bg-red-50 px-3 py-1 text-xs font-bold uppercase tracking-wider text-red-700"
          >
            <span class="size-1.5 rounded-full bg-red-600"></span>
            SECURE CUSTOMER EXPERIENCE
          </span>
          <h1 class="mt-4 text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl">
            Your facility journey
          </h1>
          <p
            class="mt-2.5 text-sm leading-6 text-slate-600 sm:text-base"
          >
            Track your linked facilities, token capacity, and account activity from one secure place.
          </p>
        </div>

        <!-- 4 KPI Metric Cards -->
        <div
          v-if="!loading && !errorMessage && (context.ois?.length || context.customer_accounts?.length)"
          class="mt-8 grid grid-cols-2 gap-3.5 sm:grid-cols-4"
          aria-label="Account overview"
        >
          <div
            class="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm backdrop-blur transition hover:border-slate-300 hover:shadow-md"
          >
            <div class="flex items-center justify-between text-slate-400 mb-2">
              <span class="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                Facilities
              </span>
              <span class="text-base">🏥</span>
            </div>
            <p class="text-2xl sm:text-3xl font-extrabold text-slate-900 leading-none">
              {{ facilityCount }}
            </p>
            <p class="mt-2 text-xs text-slate-500 font-medium">
              Linked to your account
            </p>
          </div>

          <div
            class="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm backdrop-blur transition hover:border-slate-300 hover:shadow-md"
          >
            <div class="flex items-center justify-between text-slate-400 mb-2">
              <span class="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                Token Orders
              </span>
              <span class="text-base">📦</span>
            </div>
            <p class="text-2xl sm:text-3xl font-extrabold text-red-700 leading-none">
              {{ invoiceReadyOrderCount }}
            </p>
            <p class="mt-2 text-xs text-slate-500 font-medium">
              Ready to invoice
            </p>
          </div>

          <div
            class="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm backdrop-blur transition hover:border-slate-300 hover:shadow-md"
          >
            <div class="flex items-center justify-between text-slate-400 mb-2">
              <span class="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                Open Invoices
              </span>
              <span class="text-base">💳</span>
            </div>
            <p class="text-2xl sm:text-3xl font-extrabold text-emerald-700 leading-none">
              {{ openInvoiceCount }}
            </p>
            <p class="mt-2 text-xs text-slate-500 font-medium">
              Due or awaiting payment
            </p>
          </div>

          <div
            class="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm backdrop-blur transition hover:border-slate-300 hover:shadow-md"
          >
            <div class="flex items-center justify-between text-slate-400 mb-2">
              <span class="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                Network Status
              </span>
              <span class="text-base">🛡️</span>
            </div>
            <p class="text-base sm:text-lg font-extrabold text-emerald-700 leading-none mt-1">
              Active Access
            </p>
            <p class="mt-3 text-xs text-slate-500 font-medium">
              Registry synchronized
            </p>
          </div>
        </div>
      </section>

      <!-- Feedback Banner / Notice -->
      <div
        v-if="notice"
        :role="notice.tone === 'error' ? 'alert' : 'status'"
        class="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-2xl border p-4 text-sm shadow-sm backdrop-blur"
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
          <span class="flex size-6 shrink-0 items-center justify-center rounded-lg text-sm">
            <template v-if="notice.tone === 'success'">✓</template>
            <template v-else-if="notice.tone === 'pending'">⏱</template>
            <template v-else>⚠️</template>
          </span>
          <span class="font-medium">{{ notice.text }}</span>
        </div>
        <a
          v-if="bankTransferOis"
          :href="`/payment-checkout?ois=${encodeURIComponent(bankTransferOis)}`"
          class="font-bold underline underline-offset-4 hover:opacity-80"
        >
          Other payment options →
        </a>
      </div>

      <!-- Loading State -->
      <div v-if="loading" class="mt-10 flex items-center justify-center gap-3 py-12 text-sm text-slate-500" aria-live="polite">
        <svg class="size-5 animate-spin text-red-600" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <span>Loading your secure portal…</span>
      </div>

      <!-- Error State -->
      <div
        v-else-if="errorMessage"
        class="mt-8 rounded-2xl border border-rose-200 bg-rose-50/90 p-5 text-sm text-rose-900 shadow-sm"
        role="alert"
      >
        <p class="font-medium">{{ errorMessage }}</p>
      </div>

      <!-- Empty State -->
      <section
        v-if="!loading && !errorMessage && !context.ois?.length && !context.customer_accounts?.length"
        class="mt-8 max-w-2xl rounded-3xl border border-slate-200/80 bg-white p-8 shadow-[0_8px_24px_rgba(15,23,42,0.04)]"
      >
        <span
          class="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-100 px-3 py-1 text-xs font-bold uppercase tracking-wider text-slate-700"
        >
          Account setup
        </span>
        <h2 class="mt-3 text-xl font-bold text-slate-900">
          Your account is not linked yet
        </h2>
        <p class="mt-2 text-sm leading-6 text-slate-600">
          You are signed in securely. Once your facility onboarding record is
          linked, your progress and next actions will appear here.
        </p>
      </section>

      <!-- Customer Facility Accounts Section -->
      <section
        v-if="!loading && !errorMessage && context.customer_accounts?.length"
        class="mt-10 space-y-6"
      >
        <div class="flex items-center justify-between">
          <h2 class="text-xl font-extrabold tracking-tight text-slate-900">
            Facility Accounts
          </h2>
          <span class="text-xs font-semibold text-slate-500">
            {{ context.customer_accounts.length }} Organization{{ context.customer_accounts.length > 1 ? 's' : '' }}
          </span>
        </div>

        <div class="grid gap-6 sm:grid-cols-2">
          <article
            v-for="account in context.customer_accounts"
            :key="account.customer"
            class="min-w-0 rounded-3xl border border-slate-200/80 bg-white p-6 sm:p-7 shadow-[0_8px_24px_rgba(15,23,42,0.04)] transition hover:border-slate-300 hover:shadow-md"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <span class="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-700">
                  Facility Account
                </span>
                <h3 class="mt-2 text-lg font-bold text-slate-900">
                  {{ account.organization }}
                </h3>
              </div>
              <span class="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-bold text-emerald-800">
                Onboarded
              </span>
            </div>

            <dl class="mt-4 grid grid-cols-2 gap-3 rounded-2xl border border-slate-100 bg-slate-50/70 p-3.5 text-xs">
              <div>
                <dt class="text-slate-400 font-medium">Customer ID</dt>
                <dd class="mt-0.5 font-mono font-semibold text-slate-800">{{ account.customer }}</dd>
              </div>
              <div>
                <dt class="text-slate-400 font-medium">Network</dt>
                <dd class="mt-0.5 font-semibold text-slate-800 truncate">{{ account.network || 'Being confirmed' }}</dd>
              </div>
            </dl>

            <div class="mt-5 space-y-3">
              <p class="text-xs font-bold uppercase tracking-wider text-slate-500">
                Clinics & Facilities ({{ (account.facilities || []).length }})
              </p>
              <div
                v-for="facility in account.facilities || []"
                :key="facility.mfl_code"
                class="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm transition hover:border-slate-300"
              >
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <h4 class="text-sm font-bold text-slate-900">
                      {{ facility.facility_name }}
                    </h4>
                    <div class="mt-1 flex items-center gap-2 text-xs text-slate-500">
                      <span>{{ facility.membership_status }}</span>
                      <span>·</span>
                      <span class="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-slate-700 border border-slate-200">
                        {{ facility.mfl_code }}
                      </span>
                    </div>
                  </div>
                  <span
                    class="shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-bold"
                    :class="facility.go_live ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'"
                  >
                    {{ facility.go_live ? 'Live' : 'In progress' }}
                  </span>
                </div>

                <div
                  v-if="facility.token_package || facility.package_gross_total != null"
                  class="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3 text-xs"
                >
                  <span v-if="facility.token_package" class="inline-flex items-center gap-1.5 font-medium text-slate-700">
                    <span class="text-amber-500">🪙</span>
                    <span>{{ facility.token_package }}</span>
                    <template v-if="facility.token_quantity">
                      <span class="font-bold text-slate-900">({{ facility.token_quantity.toLocaleString() }} tokens)</span>
                    </template>
                  </span>
                  <span v-if="facility.package_gross_total != null" class="font-bold text-slate-900">
                    {{ money(facility.package_gross_total, facility.package_currency) }} <span class="font-normal text-slate-500 text-[11px]">incl. VAT</span>
                  </span>
                </div>
              </div>
            </div>

            <p
              v-if="account.selected_package && !(account.facilities || []).some((facility) => facility.token_package)"
              class="mt-4 rounded-xl bg-slate-50 p-3 text-xs text-slate-600"
            >
              Selected package: <strong>{{ account.selected_package }}</strong>. Your enrollment is saved.
            </p>
          </article>
        </div>
      </section>

      <!-- Opt-In Submissions (OIS) Section -->
      <section
        v-if="!loading && !errorMessage && context.ois?.length"
        class="mt-10 space-y-6"
      >
        <div class="flex items-center justify-between">
          <h2 class="text-xl font-extrabold tracking-tight text-slate-900">
            Opt-In Requests
          </h2>
          <span class="text-xs font-semibold text-slate-500">
            {{ context.ois.length }} Active
          </span>
        </div>

        <div class="grid gap-6 sm:grid-cols-2">
          <article
            v-for="submission in context.ois"
            :key="submission.name"
            class="min-w-0 rounded-3xl border border-slate-200/80 bg-white p-6 sm:p-7 shadow-[0_8px_24px_rgba(15,23,42,0.04)]"
            :class="context.ois.length === 1 ? 'sm:col-span-2' : ''"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <span class="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-700">
                  Opt-In Request
                </span>
                <h3 class="mt-2 font-mono text-base font-bold text-slate-900">
                  {{ submission.name }}
                </h3>
              </div>
              <span class="rounded-full bg-red-50 border border-red-200 px-2.5 py-0.5 text-xs font-bold text-red-700">
                {{ submission.status || 'Pending' }}
              </span>
            </div>

            <dl class="mt-4 grid grid-cols-2 gap-3 rounded-2xl border border-slate-100 bg-slate-50/70 p-3.5 text-xs">
              <div>
                <dt class="text-slate-400 font-medium">Status</dt>
                <dd class="mt-0.5 font-semibold text-slate-800">{{ submission.status || 'Pending' }}</dd>
              </div>
              <div>
                <dt class="text-slate-400 font-medium">Network</dt>
                <dd class="mt-0.5 font-semibold text-slate-800 truncate">{{ submission.network_slug || 'Being confirmed' }}</dd>
              </div>
            </dl>

            <!-- Stepper Progress -->
            <div class="mt-6 rounded-2xl border border-slate-200/90 bg-slate-50/60 p-5">
              <div class="flex items-center justify-between gap-4">
                <p class="text-xs font-bold uppercase tracking-wider text-slate-700">
                  Onboarding Progress
                </p>
                <p class="text-xs font-semibold text-red-700">
                  {{ submission.progress?.next_action?.label }}
                </p>
              </div>
              <ol class="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <li
                  v-for="step in submission.progress?.steps || []"
                  :key="step.key"
                  class="flex items-center gap-3 rounded-xl border border-slate-200/80 bg-white p-3 text-xs shadow-sm"
                >
                  <span
                    class="flex size-7 shrink-0 items-center justify-center rounded-xl text-xs font-bold transition-all"
                    :class="stepClass(step)"
                  >
                    {{ step.status === 'complete' ? '✓' : '•' }}
                  </span>
                  <div class="min-w-0">
                    <span class="block truncate font-bold text-slate-900">{{
                      customerStepLabel(step)
                    }}</span>
                    <span class="block text-[11px] text-slate-500 font-medium">{{
                      stepLabel(step)
                    }}</span>
                  </div>
                </li>
              </ol>
            </div>

            <!-- Implementation & Facilities Status -->
            <div class="mt-5 rounded-2xl border border-slate-200/90 bg-white p-5 shadow-sm">
              <div class="flex items-center justify-between gap-3">
                <p class="text-sm font-bold text-slate-900">Implementation status</p>
                <span
                  class="rounded-full px-2.5 py-0.5 text-xs font-bold"
                  :class="
                    submission.progress?.steps?.at(-1)?.status === 'complete'
                      ? 'bg-emerald-100 text-emerald-800'
                      : 'bg-amber-100 text-amber-800'
                  "
                >
                  {{
                    submission.progress?.steps?.at(-1)?.status === 'complete'
                      ? 'Ready for service activation'
                      : 'In progress'
                  }}
                </span>
              </div>
              <p class="mt-2 text-xs leading-5 text-slate-600">
                <template v-if="isSelfOnboarded(submission)">
                  <span v-if="submission.progress?.package?.display_name">
                    Selected package: <strong>{{ submission.progress.package.display_name }}</strong>.
                  </span>
                  Payment status: <strong>{{ submission.progress?.payment_status || 'Not started' }}</strong>.
                </template>
                <template v-else>
                  {{ contractSummary(submission.progress) }}.
                </template>
                Your network’s service status is shown below.
              </p>

              <div class="mt-4 space-y-2.5">
                <div
                  v-for="facility in submission.progress?.facilities || []"
                  :key="facility.mfl_code"
                  class="flex items-center justify-between gap-3 rounded-xl border border-slate-200/80 bg-slate-50/70 px-3.5 py-2.5 text-xs shadow-sm"
                >
                  <div>
                    <span class="block font-bold text-slate-900">{{
                      facility.facility_name
                    }}</span>
                    <span class="text-slate-500"
                      >{{ facility.membership_status }} ·
                      {{ facility.mfl_code }}</span
                    >
                  </div>
                  <span
                    class="shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-bold"
                    :class="
                      facility.network_contact?.go_live
                        ? 'bg-emerald-100 text-emerald-800'
                        : 'bg-slate-100 text-slate-600'
                    "
                  >
                    {{
                      facility.network_contact?.go_live
                        ? 'Live'
                        : 'Not yet live'
                    }}
                  </span>
                </div>
              </div>

              <!-- Open Invoices -->
              <div
                v-if="submission.open_invoices?.length"
                class="mt-5 border-t border-slate-100 pt-5"
              >
                <p class="text-xs font-bold uppercase tracking-wider text-slate-700">
                  Open invoices ({{ submission.open_invoices.length }})
                </p>
                <div
                  v-for="invoice in submission.open_invoices"
                  :key="invoice.name"
                  class="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200/80 bg-white p-4 text-xs shadow-sm"
                >
                  <div>
                    <span class="block font-bold text-slate-900 text-sm">{{
                      invoice.invoice_number
                    }}</span>
                    <span class="text-slate-500"
                      >Due {{ invoice.due_date || 'on request' }} ·
                      <span
                        :class="
                          invoiceStatus(invoice).key === 'overdue'
                            ? 'font-bold text-rose-600'
                            : 'font-medium'
                        "
                        >{{ invoiceStatus(invoice).label }}</span
                      ></span
                    >
                  </div>
                  <button
                    type="button"
                    class="inline-flex min-h-10 items-center gap-1.5 rounded-xl bg-gradient-to-r from-red-600 to-rose-700 px-4 py-2 text-xs font-semibold text-white shadow-md shadow-red-600/20 transition-all hover:from-red-700 hover:to-rose-800 disabled:opacity-50"
                    :disabled="busyId === invoice.name"
                    @click="payInvoice(submission.name, invoice)"
                  >
                    {{
                      busyId === invoice.name
                        ? 'Opening checkout…'
                        : `Make payment · ${money(invoice.amount, invoice.currency)}`
                    }}
                  </button>
                </div>
              </div>

              <!-- Token Orders -->
              <div
                v-if="submission.open_orders?.length"
                class="mt-5 border-t border-slate-100 pt-5"
              >
                <p class="text-xs font-bold uppercase tracking-wider text-slate-700">
                  Token orders ({{ submission.open_orders.length }})
                </p>
                <div
                  v-for="order in submission.open_orders"
                  :key="order.name"
                  class="mt-3 rounded-xl border border-slate-200/80 bg-white p-4 text-xs shadow-sm"
                >
                  <div class="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <span class="block font-bold text-slate-900 text-sm">{{
                        packageLabel(
                          order.crm_token_package_item,
                          context.token_packages,
                        )
                      }}</span>
                      <span class="text-slate-500"
                        >{{
                          facilityLabel(
                            order.crm_token_facility_mfl,
                            submission.progress?.facilities,
                          )
                        }}
                        · {{ order.name }} ·
                        <strong class="text-slate-900">{{ money(order.grand_total, order.currency) }}</strong> incl. VAT</span
                      >
                    </div>
                    <button
                      v-if="order.can_create_invoice"
                      type="button"
                      class="inline-flex min-h-10 items-center gap-1.5 rounded-xl bg-gradient-to-r from-red-600 to-rose-700 px-4 py-2 text-xs font-semibold text-white shadow-md shadow-red-600/20 transition-all hover:from-red-700 hover:to-rose-800 disabled:opacity-50"
                      :disabled="busyId === order.name"
                      @click="createInvoice(order.name)"
                    >
                      {{
                        busyId === order.name
                          ? 'Creating invoice…'
                          : 'Create invoice'
                      }}
                    </button>
                    <p v-else class="text-slate-500 font-medium">
                      {{ invoiceUnavailableMessage(order) }}
                    </p>
                  </div>
                  <p v-if="order.can_create_invoice" class="mt-2 text-slate-500 text-[11px]">
                    Create an invoice for this order. When it is due, return here and make payment.
                  </p>
                </div>
              </div>
            </div>
          </article>
        </div>
      </section>

      <!-- Token Catalogue Section -->
      <section
        v-if="!loading && !errorMessage && context.ois?.length && context.token_packages?.length"
        class="mt-10 rounded-3xl border border-slate-200/80 bg-white p-6 sm:p-8 shadow-[0_10px_30px_rgba(15,23,42,0.04)]"
      >
        <div class="flex flex-wrap items-end justify-between gap-4">
          <div>
            <span
              class="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-100 px-3 py-1 text-xs font-bold uppercase tracking-wider text-slate-700"
            >
              Token catalogue
            </span>
            <h2 class="mt-2 text-2xl font-extrabold tracking-tight text-slate-900">
              Choose capacity when you need it
            </h2>
          </div>
          <p class="text-xs font-medium text-slate-500">All prices exclude VAT</p>
        </div>

        <div class="mt-6 grid gap-4 sm:grid-cols-2">
          <div>
            <label class="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
              Opt-In Request
            </label>
            <select
              v-model="purchaseOis"
              class="w-full rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-900 shadow-sm transition focus:border-red-600 focus:outline-none focus:ring-4 focus:ring-red-600/10"
              @change="
                purchaseFacility = purchaseFacilities()?.[0]?.mfl_code || ''
              "
            >
              <option
                v-for="item in context.ois"
                :key="item.name"
                :value="item.name"
              >
                {{ item.name }}
              </option>
            </select>
          </div>
          <div>
            <label class="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
              Target Facility
            </label>
            <select
              v-model="purchaseFacility"
              class="w-full rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-900 shadow-sm transition focus:border-red-600 focus:outline-none focus:ring-4 focus:ring-red-600/10"
            >
              <option
                v-for="facility in purchaseFacilities()"
                :key="facility.mfl_code"
                :value="facility.mfl_code"
              >
                {{ facility.facility_name }} · {{ facility.mfl_code }}
              </option>
            </select>
          </div>
        </div>

        <p
          v-if="purchaseMessage"
          class="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-3.5 text-xs font-medium text-slate-700"
        >
          {{ purchaseMessage }}
        </p>

        <div class="mt-7 grid gap-5 md:grid-cols-3">
          <article
            v-for="item in context.token_packages"
            :key="item.item_code"
            class="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-sm transition hover:border-slate-300 hover:shadow-md flex flex-col justify-between"
          >
            <div>
              <div class="flex items-center justify-between">
                <h3 class="text-base font-bold text-slate-900">
                  {{ item.display_name || item.item_code }}
                </h3>
                <span
                  v-if="Number(item.price_ex_vat ?? item.price ?? 0) === 0"
                  class="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-800"
                >
                  Free Tier
                </span>
              </div>
              <p class="mt-3 text-2xl font-extrabold text-slate-900">
                {{ Number(item.price_ex_vat ?? item.price ?? 0) === 0 ? '$0' : money(item.price_ex_vat ?? item.price, item.currency) }}
                <span class="text-xs font-normal text-slate-500">excl. VAT</span>
              </p>
              <p v-if="item.gross_total" class="mt-1 text-xs text-slate-500">
                {{ item.vat_label || 'VAT' }}
                {{ money(item.vat_amount, item.currency) }} · Total
                <strong class="text-slate-800">{{ money(item.gross_total, item.currency) }}</strong>
              </p>
              <div class="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-700">
                <span>🪙</span>
                <span>{{ item.token_quantity || 100 }} Tokens</span>
              </div>
              <p class="mt-3 text-xs leading-relaxed text-slate-600">
                {{ item.coverage_summary || item.description }}
              </p>
            </div>

            <button
              class="mt-5 flex min-h-11 w-full items-center justify-center gap-1.5 rounded-xl bg-gradient-to-r from-red-600 to-rose-700 px-4 py-2.5 text-xs font-semibold text-white shadow-md shadow-red-600/20 transition-all hover:from-red-700 hover:to-rose-800 hover:shadow-lg disabled:opacity-50"
              type="button"
              :disabled="purchaseBusy"
              @click="buyPackage(item)"
            >
              {{
                purchaseBusy
                  ? 'Working…'
                  : existingOrder(item)
                    ? `Resume order ${existingOrder(item).name}`
                    : 'Create order'
              }}
            </button>
          </article>
        </div>
      </section>
    </div>
  </main>
</template>

