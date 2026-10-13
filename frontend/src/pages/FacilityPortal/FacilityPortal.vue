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
const context = ref({ user: '', ois: [] })
const facilityCount = computed(() =>
  (context.value.ois || []).reduce(
    (total, submission) =>
      total + (submission.progress?.facilities?.length || 0),
    0,
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
  <main class="min-h-screen bg-[#f6f7f8] text-ink-gray-9">
    <header class="border-b border-outline-gray-2 bg-surface-white">
      <div
        class="mx-auto flex max-w-5xl items-center justify-between px-5 py-4 sm:px-8"
      >
        <div>
          <p class="text-sm font-semibold tracking-tight">
            Tiberbu Customer Experience
          </p>
          <p class="text-xs text-ink-gray-5">Secure facility portal</p>
        </div>
        <a
          class="text-sm text-ink-gray-6 underline underline-offset-4 hover:text-ink-gray-9"
          href="/api/method/logout"
          >Sign out</a
        >
      </div>
    </header>

    <div class="mx-auto max-w-5xl px-5 py-10 sm:px-8 sm:py-14">
      <section
        class="relative isolate mt-8 overflow-hidden rounded-2xl border border-[#f0d6d8] bg-gradient-to-br from-[#fff5f5] via-white to-[#f1faf6] p-5 shadow-[0_10px_24px_rgba(15,23,42,0.05)] sm:p-7"
      >
        <div
          class="pointer-events-none absolute -right-14 -top-20 size-56 rounded-full bg-[radial-gradient(circle,rgba(188,24,35,0.12)_0%,rgba(188,24,35,0.02)_58%,transparent_72%)]"
          aria-hidden="true"
        />
        <div
          class="pointer-events-none absolute -bottom-28 left-1/4 size-64 rounded-full bg-[radial-gradient(circle,rgba(16,185,129,0.11)_0%,rgba(16,185,129,0.02)_58%,transparent_72%)]"
          aria-hidden="true"
        />
        <div
          class="relative z-10 grid gap-6 lg:grid-cols-[minmax(0,1.3fr)_minmax(280px,.9fr)] lg:items-center"
        >
          <div>
            <span
              class="inline-flex items-center rounded-full border border-[#edc5c8] bg-white/80 px-3 py-1 text-[11px] font-semibold tracking-wide text-[#9e1720] shadow-sm backdrop-blur"
            >
              SECURE CUSTOMER EXPERIENCE
            </span>
            <h1 class="mt-4 text-3xl font-semibold tracking-tight sm:text-4xl">
              Your facility journey
            </h1>
            <p
              class="mt-3 max-w-2xl text-sm leading-6 text-ink-gray-6 sm:text-base sm:leading-7"
            >
              Follow Opt-In progress, review token orders, create invoices, and
              make payments from one secure place.
            </p>
          </div>
          <div
            v-if="!loading && !errorMessage && context.ois?.length"
            class="grid grid-cols-2 gap-3 sm:grid-cols-3"
            aria-label="Account overview"
          >
            <div
              class="rounded-xl border border-white/80 bg-white/75 p-3 shadow-sm backdrop-blur-md sm:p-4"
            >
              <p
                class="text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-gray-5"
              >
                Facilities
              </p>
              <p
                class="mt-1 text-2xl font-bold leading-none tracking-tight text-[#bc1823]"
              >
                {{ facilityCount }}
              </p>
              <p class="mt-2 text-[11px] text-ink-gray-5">
                Linked to your account
              </p>
            </div>
            <div
              class="rounded-xl border border-white/80 bg-white/75 p-3 shadow-sm backdrop-blur-md sm:p-4"
            >
              <p
                class="text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-gray-5"
              >
                Orders ready for invoicing
              </p>
              <p
                class="mt-1 text-2xl font-bold leading-none tracking-tight text-[#bc1823]"
              >
                {{ invoiceReadyOrderCount }}
              </p>
              <p class="mt-2 text-[11px] text-ink-gray-5">
                Ready to invoice
              </p>
            </div>
            <div
              class="col-span-2 rounded-xl border border-white/80 bg-white/75 p-3 shadow-sm backdrop-blur-md sm:col-span-1 sm:p-4"
            >
              <p
                class="text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-gray-5"
              >
                Open invoices
              </p>
              <p
                class="mt-1 text-2xl font-bold leading-none tracking-tight text-emerald-700"
              >
                {{ openInvoiceCount }}
              </p>
              <p class="mt-2 text-[11px] text-ink-gray-5">
                Due or awaiting payment
              </p>
            </div>
          </div>
        </div>
      </section>

      <div
        v-if="notice"
        :role="notice.tone === 'error' ? 'alert' : 'status'"
        class="mt-6 rounded-xl border px-4 py-3 text-sm shadow-sm backdrop-blur"
        :class="{
          'border-emerald-200 bg-emerald-50/90 text-emerald-800':
            notice.tone === 'success',
          'border-amber-200 bg-amber-50/90 text-amber-800':
            notice.tone === 'pending',
          'border border-outline-red-2 bg-surface-red-1 text-ink-red-7':
            notice.tone === 'error',
        }"
      >
        {{ notice.text }}
        <a
          v-if="bankTransferOis"
          :href="`/payment-checkout?ois=${encodeURIComponent(bankTransferOis)}`"
          class="ml-1 font-semibold underline underline-offset-4"
          >Other payment options</a
        >
      </div>
      <p v-if="loading" class="mt-8 text-sm text-ink-gray-5" aria-live="polite">
        Loading your secure portal…
      </p>
      <p
        v-else-if="errorMessage"
        class="mt-8 rounded-xl border border-outline-red-2 bg-surface-red-1 px-4 py-3 text-sm text-ink-red-7 shadow-sm"
        role="alert"
      >
        {{ errorMessage }}
      </p>
      <section
        v-else-if="!context.ois?.length"
        class="mt-8 max-w-2xl rounded-2xl border border-white/80 bg-white/90 p-6 shadow-[0_8px_24px_rgba(15,23,42,0.05)] backdrop-blur-sm"
      >
        <p
          class="text-xs font-semibold uppercase tracking-[0.14em] text-ink-gray-5"
        >
          Account setup
        </p>
        <h2 class="mt-2 text-xl font-semibold">
          Your account is not linked yet
        </h2>
        <p class="mt-3 text-sm leading-6 text-ink-gray-6">
          You are signed in securely. Once your facility onboarding record is
          linked, your progress and next actions will appear here.
        </p>
      </section>
      <section v-else class="mt-8 grid gap-4 sm:grid-cols-2">
        <article
          v-for="submission in context.ois"
          :key="submission.name"
          class="min-w-0 rounded-2xl border border-white/80 bg-white/90 p-5 shadow-[0_8px_24px_rgba(15,23,42,0.05)] backdrop-blur-sm sm:p-6"
          :class="context.ois.length === 1 ? 'sm:col-span-2' : ''"
        >
          <p
            class="text-xs font-semibold uppercase tracking-[0.14em] text-ink-gray-5"
          >
            Opt-In Request
          </p>
          <h2 class="mt-2 font-mono text-lg font-semibold">
            {{ submission.name }}
          </h2>
          <dl class="mt-5 space-y-3 text-sm">
            <div class="flex justify-between gap-4">
              <dt class="text-ink-gray-5">Status</dt>
              <dd class="font-medium">{{ submission.status || 'Pending' }}</dd>
            </div>
            <div class="flex justify-between gap-4">
              <dt class="text-ink-gray-5">Network</dt>
              <dd class="font-medium">
                {{ submission.network_slug || 'Being confirmed' }}
              </dd>
            </div>
          </dl>
          <div
            class="mt-6 rounded-xl border border-outline-gray-1 bg-white/65 p-4 shadow-sm sm:p-5"
          >
            <div class="flex items-center justify-between gap-4">
              <p
                class="text-xs font-semibold uppercase tracking-[0.12em] text-ink-gray-5"
              >
                Progress
              </p>
              <p class="text-xs font-medium text-ink-gray-6">
                {{ submission.progress?.next_action?.label }}
              </p>
            </div>
            <ol class="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <li
                v-for="step in submission.progress?.steps || []"
                :key="step.key"
                class="flex items-center gap-3 rounded-lg border border-outline-gray-1 bg-white/80 p-3 text-xs shadow-sm"
              >
                <span
                  class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold"
                  :class="stepClass(step)"
                >
                  {{ step.status === 'complete' ? '✓' : '•' }}
                </span>
                <span>
                  <span class="block font-medium text-ink-gray-8">{{
                    customerStepLabel(step)
                  }}</span>
                  <span class="block text-ink-gray-5">{{
                    stepLabel(step)
                  }}</span>
                </span>
              </li>
            </ol>
          </div>

          <div
            class="mt-4 rounded-xl border border-outline-gray-1 bg-gradient-to-br from-white/90 to-surface-gray-1 p-4 shadow-sm"
          >
            <div class="flex items-center justify-between gap-3">
              <p class="text-sm font-medium">Implementation status</p>
              <span
                class="rounded-full px-2 py-1 text-xs font-medium"
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
            <p class="mt-2 text-sm leading-6 text-ink-gray-6">
              <template v-if="isSelfOnboarded(submission)">
                <span v-if="submission.progress?.package?.display_name">
                  Selected package:
                  {{ submission.progress.package.display_name }}.
                </span>
                Payment status:
                {{ submission.progress?.payment_status || 'Not started' }}.
              </template>
              <template v-else>
                {{ contractSummary(submission.progress) }}.
              </template>
              Your network’s service status is shown below.
            </p>
            <div class="mt-3 space-y-2">
              <div
                v-for="facility in submission.progress?.facilities || []"
                :key="facility.mfl_code"
                class="flex items-center justify-between gap-3 rounded-lg border border-outline-gray-1 bg-white/85 px-3 py-3 text-xs shadow-sm"
              >
                <span>
                  <span class="block font-medium text-ink-gray-8">{{
                    facility.facility_name
                  }}</span>
                  <span class="text-ink-gray-5"
                    >{{ facility.membership_status }} ·
                    {{ facility.mfl_code }}</span
                  >
                </span>
                <span
                  class="shrink-0 rounded-full px-2 py-1 font-medium"
                  :class="
                    facility.network_contact?.go_live
                      ? 'bg-emerald-100 text-emerald-800'
                      : 'bg-surface-gray-2 text-ink-gray-6'
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
            <div
              v-if="submission.open_invoices?.length"
              class="mt-4 border-t border-outline-gray-2 pt-4"
            >
              <p
                class="text-xs font-semibold uppercase tracking-[0.12em] text-ink-gray-5"
              >
                Open invoices
              </p>
              <div
                v-for="invoice in submission.open_invoices"
                :key="invoice.name"
                class="mt-2 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-outline-gray-1 bg-white/85 px-3 py-3 text-xs shadow-sm"
              >
                <span
                  ><span class="block font-medium">{{
                    invoice.invoice_number
                  }}</span
                  ><span class="text-ink-gray-5"
                    >Due {{ invoice.due_date || 'on request' }} ·
                    <span
                      :class="
                        invoiceStatus(invoice).key === 'overdue'
                          ? 'font-semibold text-ink-red-7'
                          : ''
                      "
                      >{{ invoiceStatus(invoice).label }}</span
                    ></span
                  ></span
                >
                <button
                  type="button"
                  class="min-h-10 rounded-md bg-[#bc1823] px-4 py-2 font-semibold text-white disabled:opacity-50"
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
            <div
              v-if="submission.open_orders?.length"
              class="mt-4 border-t border-outline-gray-2 pt-4"
            >
              <p
                class="text-xs font-semibold uppercase tracking-[0.12em] text-ink-gray-5"
              >
                Token orders
              </p>
              <div
                v-for="order in submission.open_orders"
                :key="order.name"
                class="mt-2 rounded-lg border border-outline-gray-1 bg-white/85 px-3 py-3 text-xs shadow-sm"
              >
                <div class="flex flex-wrap items-center justify-between gap-3">
                  <span
                    ><span class="block font-medium">{{
                      packageLabel(
                        order.crm_token_package_item,
                        context.token_packages,
                      )
                    }}</span
                    ><span class="text-ink-gray-5"
                      >{{
                        facilityLabel(
                          order.crm_token_facility_mfl,
                          submission.progress?.facilities,
                        )
                      }}
                      · {{ order.name }} ·
                      {{ money(order.grand_total, order.currency) }} incl.
                      VAT</span
                    ></span
                  >
                  <button
                    v-if="order.can_create_invoice"
                    type="button"
                    class="min-h-10 rounded-md bg-[#bc1823] px-4 py-2 font-semibold text-white disabled:opacity-50"
                    :disabled="busyId === order.name"
                    @click="createInvoice(order.name)"
                  >
                    {{
                      busyId === order.name
                        ? 'Creating invoice…'
                        : 'Create invoice'
                    }}
                  </button>
                  <p v-else class="text-ink-gray-5">
                    {{ invoiceUnavailableMessage(order) }}
                  </p>
                </div>
                <p v-if="order.can_create_invoice" class="mt-2 text-ink-gray-5">
                  Create an invoice for this order. When it is due, return here
                  and make payment.
                </p>
              </div>
            </div>
          </div>
        </article>
      </section>
      <section
        v-if="!loading && !errorMessage && context.token_packages?.length"
        class="mt-8 rounded-2xl border border-white/80 bg-white/90 p-5 shadow-[0_8px_24px_rgba(15,23,42,0.05)] backdrop-blur-sm sm:p-6"
      >
        <div class="flex items-end justify-between gap-4">
          <div>
            <p
              class="text-xs font-semibold uppercase tracking-[0.14em] text-ink-gray-5"
            >
              Token catalogue
            </p>
            <h2 class="mt-2 text-xl font-semibold">
              Choose capacity when you need it
            </h2>
          </div>
          <p class="text-xs text-ink-gray-5">All prices exclude VAT</p>
        </div>
        <div class="mt-5 grid gap-3 sm:grid-cols-2">
          <select
            v-model="purchaseOis"
            class="w-full min-w-0 rounded-lg border border-outline-gray-2 px-3 py-2 text-sm"
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
            </option></select
          ><select
            v-model="purchaseFacility"
            class="w-full min-w-0 rounded-lg border border-outline-gray-2 px-3 py-2 text-sm"
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
        <p
          v-if="purchaseMessage"
          class="mt-3 rounded-lg bg-surface-gray-1 px-3 py-2 text-xs text-ink-gray-6"
        >
          {{ purchaseMessage }}
        </p>
        <div class="mt-5 grid gap-3 md:grid-cols-3">
          <article
            v-for="item in context.token_packages"
            :key="item.item_code"
            class="rounded-xl border border-outline-gray-1 bg-white/75 p-4 shadow-sm transition-shadow hover:shadow-md"
          >
            <p class="text-sm font-semibold">
              {{ item.display_name || item.item_code }}
            </p>
            <p class="mt-2 text-base font-semibold">
              {{ money(item.price_ex_vat ?? item.price, item.currency) }}
              <span class="text-xs font-normal text-ink-gray-5">excl. VAT</span>
            </p>
            <p v-if="item.gross_total" class="mt-1 text-xs text-ink-gray-5">
              {{ item.vat_label || 'VAT' }}
              {{ money(item.vat_amount, item.currency) }} · Total
              {{ money(item.gross_total, item.currency) }}
            </p>
            <p class="mt-2 text-xs leading-5 text-ink-gray-5">
              {{ item.coverage_summary || item.description }}
            </p>
            <button
              class="mt-4 min-h-10 rounded-md bg-[#bc1823] px-4 py-2 text-xs font-semibold text-white disabled:opacity-50"
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
