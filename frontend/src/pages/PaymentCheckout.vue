<template>
  <main class="min-h-screen bg-surface-gray-1 px-4 py-8 text-ink-gray-9 sm:px-8">
    <div class="mx-auto w-full max-w-5xl">
      <header class="mb-8">
        <p class="text-xs font-semibold uppercase tracking-[0.18em] text-ink-gray-5">
          {{ network?.display_name || 'Tiberbu Healthnet' }}
        </p>
        <h1 class="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">
          Pay an outstanding invoice
        </h1>
        <p class="mt-2 max-w-2xl text-sm text-ink-gray-6">
          Enter the OIS reference from your opt-in confirmation. We will send a one-time code to the facility signatory before showing any invoices.
        </p>
      </header>

      <section v-if="!sessionToken && !otpSent" class="mx-auto max-w-xl rounded-2xl border border-outline-gray-2 bg-surface-white p-6 shadow-sm sm:p-8">
        <label class="block text-sm font-medium text-ink-gray-8" for="ois-number">OIS number</label>
        <input
          id="ois-number"
          v-model="oisNumber"
          class="mt-2 w-full rounded-lg border border-outline-gray-3 bg-surface-white px-3 py-2.5 text-base outline-none focus:border-ink-blue-5 focus:ring-2 focus:ring-ink-blue-2"
          placeholder="e.g. OIS-2026-00001"
          autocomplete="off"
          @keyup.enter="requestOtp"
        />
        <p class="mt-2 text-xs text-ink-gray-5">The code goes to the facility signatory saved on the OIS.</p>
        <p v-if="errorMessage" class="mt-4 rounded-lg bg-surface-red-1 px-3 py-2 text-sm text-ink-red-7">{{ errorMessage }}</p>
        <button
          class="mt-6 w-full rounded-lg bg-ink-gray-9 px-4 py-3 text-sm font-semibold text-white transition hover:bg-ink-gray-8 disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="loading || !oisNumber.trim()"
          @click="requestOtp"
        >
          {{ loading ? 'Sending code…' : 'Send verification code' }}
        </button>
      </section>

      <section v-else-if="!sessionToken && otpSent" class="mx-auto max-w-xl rounded-2xl border border-outline-gray-2 bg-surface-white p-6 shadow-sm sm:p-8">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-xs font-semibold uppercase tracking-wide text-ink-gray-5">Verify access</p>
            <h2 class="mt-1 text-xl font-semibold">Check the signatory’s email</h2>
          </div>
          <span class="rounded-full bg-surface-gray-2 px-3 py-1 text-xs font-medium text-ink-gray-6">{{ oisNumber }}</span>
        </div>
        <p class="mt-4 text-sm text-ink-gray-6">Enter the six-digit code sent to the facility signatory. The code expires in 10 minutes.</p>
        <input
          v-model="otp"
          class="mt-5 w-full rounded-lg border border-outline-gray-3 px-3 py-3 text-center text-2xl tracking-[0.45em] outline-none focus:border-ink-blue-5 focus:ring-2 focus:ring-ink-blue-2"
          inputmode="numeric"
          maxlength="6"
          autocomplete="one-time-code"
          placeholder="••••••"
          @keyup.enter="verifyOtp"
        />
        <p v-if="errorMessage" class="mt-4 rounded-lg bg-surface-red-1 px-3 py-2 text-sm text-ink-red-7">{{ errorMessage }}</p>
        <div class="mt-6 flex gap-3">
          <button class="flex-1 rounded-lg border border-outline-gray-3 px-4 py-3 text-sm font-semibold text-ink-gray-7 hover:bg-surface-gray-1" @click="reset">Start over</button>
          <button class="flex-1 rounded-lg bg-ink-gray-9 px-4 py-3 text-sm font-semibold text-white hover:bg-ink-gray-8 disabled:opacity-50" :disabled="loading || otp.trim().length < 6" @click="verifyOtp">{{ loading ? 'Checking…' : 'View invoices' }}</button>
        </div>
      </section>

      <section v-else>
        <div class="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p class="text-xs font-semibold uppercase tracking-wide text-ink-gray-5">Secure checkout · {{ oisNumber }}</p>
            <h2 class="mt-1 text-2xl font-semibold">Outstanding invoices</h2>
          </div>
          <button class="text-sm text-ink-gray-6 underline hover:text-ink-gray-9" @click="reset">Use another OIS</button>
        </div>

        <div v-if="callbackMessage" class="mb-5 rounded-xl border border-outline-green-2 bg-surface-green-1 px-4 py-3 text-sm text-ink-green-8">{{ callbackMessage }}</div>
        <div v-if="errorMessage" class="mb-5 rounded-xl border border-outline-red-2 bg-surface-red-1 px-4 py-3 text-sm text-ink-red-7">{{ errorMessage }}</div>

        <div v-if="!invoices.length" class="rounded-2xl border border-outline-gray-2 bg-surface-white p-8 text-center shadow-sm">
          <h3 class="text-lg font-semibold">No payment due</h3>
          <p class="mt-2 text-sm text-ink-gray-6">There are no submitted invoices with an outstanding balance for this OIS.</p>
        </div>
        <div v-else class="grid gap-4 lg:grid-cols-2">
          <article v-for="invoice in invoices" :key="invoice.name" class="rounded-2xl border border-outline-gray-2 bg-surface-white p-5 shadow-sm">
            <div class="flex items-start justify-between gap-4">
              <div>
                <p class="text-xs font-semibold uppercase tracking-wide text-ink-gray-5">{{ invoice.invoice_number }}</p>
                <p class="mt-1 text-sm text-ink-gray-6">Due {{ humanDate(invoice.due_date) }}</p>
              </div>
              <p class="text-xl font-bold tabular-nums">{{ formatMoney(invoice.amount, invoice.currency) }}</p>
            </div>
            <div class="mt-5 grid gap-2 sm:grid-cols-2">
              <button
                v-if="paystack.enabled"
                class="rounded-lg bg-ink-gray-9 px-3 py-2.5 text-sm font-semibold text-white hover:bg-ink-gray-8 disabled:opacity-50"
                :disabled="paying === invoice.name"
                @click="payWithPaystack(invoice)"
              >{{ paying === invoice.name ? 'Opening…' : 'Pay securely online' }}</button>
              <button class="rounded-lg border border-outline-gray-3 px-3 py-2.5 text-sm font-semibold text-ink-gray-7 hover:bg-surface-gray-1" @click="openTransfer(invoice)">Bank transfer</button>
            </div>
            <div v-if="transferInvoice?.name === invoice.name" class="mt-4 rounded-xl bg-surface-gray-1 p-4">
              <p class="text-sm font-semibold">Transfer to {{ bankDetails.bank }}</p>
              <dl class="mt-3 grid grid-cols-2 gap-y-2 text-sm">
                <dt class="text-ink-gray-5">Account name</dt><dd class="text-right font-medium">{{ bankDetails.account_name }}</dd>
                <dt class="text-ink-gray-5">Account number</dt><dd class="text-right font-medium">{{ bankDetails.account_number }}</dd>
                <dt class="text-ink-gray-5">Branch</dt><dd class="text-right font-medium">{{ bankDetails.branch }}</dd>
              </dl>
              <p class="mt-3 text-xs text-ink-gray-5">After transferring, submit the reference below. Finance will reconcile and submit the receipt; your invoice is not marked paid automatically.</p>
              <input v-model="transferReference" class="mt-3 w-full rounded-lg border border-outline-gray-3 bg-surface-white px-3 py-2 text-sm" placeholder="Bank transfer reference" />
              <button class="mt-3 w-full rounded-lg bg-ink-gray-9 px-3 py-2.5 text-sm font-semibold text-white hover:bg-ink-gray-8 disabled:opacity-50" :disabled="loading || !transferReference.trim()" @click="reportTransfer(invoice)">{{ loading ? 'Submitting…' : 'Submit transfer for reconciliation' }}</button>
            </div>
          </article>
        </div>

        <p class="mt-6 text-xs leading-5 text-ink-gray-5">Payments are recorded against the submitted invoice. Paystack payments are verified with Paystack before the receipt is submitted. Bank transfers remain pending until finance confirms the bank statement.</p>
      </section>
    </div>
  </main>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { createResource } from 'frappe-ui'

const props = defineProps({ initialOis: { type: String, default: '' } })
const oisNumber = ref(props.initialOis || new URLSearchParams(window.location.search).get('ois') || '')
const otp = ref('')
const otpSent = ref(false)
const sessionToken = ref('')
const checkout = ref(null)
const loading = ref(false)
const paying = ref('')
const errorMessage = ref('')
const callbackMessage = ref('')
const transferInvoice = ref(null)
const transferReference = ref('')

const requestOtpResource = createResource({ url: 'crm.api.checkout.request_payment_otp' })
const verifyOtpResource = createResource({ url: 'crm.api.checkout.verify_payment_otp' })
const checkoutResource = createResource({ url: 'crm.api.checkout.get_payment_checkout' })
const paystackResource = createResource({ url: 'crm.api.checkout.initialize_paystack_payment' })
const verifyPaystackResource = createResource({ url: 'crm.api.checkout.verify_paystack_payment' })
const transferResource = createResource({ url: 'crm.api.checkout.report_bank_transfer' })

const verified = computed(() => Boolean(sessionToken.value && checkout.value))
const network = computed(() => checkout.value?.network || {})
const invoices = computed(() => checkout.value?.invoices || [])
const bankDetails = computed(() => checkout.value?.bank_details || {})
const paystack = computed(() => checkout.value?.paystack || { enabled: false })

function friendlyError(error) {
  return error?.messages?.[0] || error?.message || 'We could not complete that request. Please try again.'
}

async function requestOtp() {
  loading.value = true
  errorMessage.value = ''
  try {
    await requestOtpResource.submit({ ois_number: oisNumber.value.trim() })
    otp.value = ''
    otpSent.value = true
  } catch (error) {
    errorMessage.value = friendlyError(error)
  } finally {
    loading.value = false
  }
}

async function verifyOtp() {
  loading.value = true
  errorMessage.value = ''
  try {
    const result = await verifyOtpResource.submit({ ois_number: oisNumber.value.trim(), otp: otp.value.trim() })
    sessionToken.value = result.session_token
    sessionStorage.setItem(`crm-checkout:${oisNumber.value.trim()}`, sessionToken.value)
    checkout.value = result
    await loadCheckout()
  } catch (error) {
    errorMessage.value = friendlyError(error)
  } finally {
    loading.value = false
  }
}

async function loadCheckout() {
  const result = await checkoutResource.submit({ session_token: sessionToken.value })
  checkout.value = result
  const reference = new URLSearchParams(window.location.search).get('reference')
  if (reference) {
    const payment = await verifyPaystackResource.submit({ session_token: sessionToken.value, reference })
    callbackMessage.value = payment.paid ? `Payment received for ${payment.invoice}.` : 'Payment is still being confirmed. Refresh shortly.'
  }
}

async function payWithPaystack(invoice) {
  paying.value = invoice.name
  errorMessage.value = ''
  try {
    const result = await paystackResource.submit({ session_token: sessionToken.value, invoice: invoice.name })
    window.location.href = result.authorization_url
  } catch (error) {
    errorMessage.value = friendlyError(error)
  } finally {
    paying.value = ''
  }
}

function openTransfer(invoice) {
  transferInvoice.value = transferInvoice.value?.name === invoice.name ? null : invoice
  transferReference.value = ''
  errorMessage.value = ''
}

async function reportTransfer(invoice) {
  loading.value = true
  errorMessage.value = ''
  try {
    await transferResource.submit({ session_token: sessionToken.value, invoice: invoice.name, reference_no: transferReference.value.trim() })
    callbackMessage.value = 'Transfer submitted for finance reconciliation. The invoice will be marked paid after confirmation.'
    transferInvoice.value = null
    transferReference.value = ''
    await loadCheckout()
  } catch (error) {
    errorMessage.value = friendlyError(error)
  } finally {
    loading.value = false
  }
}

function reset() {
  sessionToken.value = ''
  otpSent.value = false
  checkout.value = null
  otp.value = ''
  errorMessage.value = ''
  callbackMessage.value = ''
  transferInvoice.value = null
}

function formatMoney(value, currency) {
  return `${currency || 'KES'} ${Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function humanDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

onMounted(async () => {
  const saved = sessionStorage.getItem(`crm-checkout:${oisNumber.value.trim()}`)
  if (!saved || !oisNumber.value.trim()) return
  sessionToken.value = saved
  try {
    await loadCheckout()
  } catch {
    sessionStorage.removeItem(`crm-checkout:${oisNumber.value.trim()}`)
    sessionToken.value = ''
  }
})
</script>
