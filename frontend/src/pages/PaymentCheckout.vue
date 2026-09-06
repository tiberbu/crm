<template>
  <main class="min-h-screen bg-[#f6f7f8] text-ink-gray-9">
    <header class="border-b border-outline-gray-2 bg-surface-white">
      <div
        class="mx-auto flex max-w-6xl items-center justify-between px-5 py-4 sm:px-8"
      >
        <div class="flex items-center gap-3">
          <span
            class="flex size-9 items-center justify-center rounded-xl text-sm font-bold text-white shadow-sm"
            :style="{ backgroundColor: brandColor }"
            aria-hidden="true"
            >C</span
          >
          <div>
            <p class="text-sm font-semibold tracking-tight">{{ brandName }}</p>
            <p class="text-xs text-ink-gray-5">Secure invoice payments</p>
          </div>
        </div>
        <div class="hidden items-center gap-2 text-xs text-ink-gray-5 sm:flex">
          <span class="size-2 rounded-full bg-green-500" aria-hidden="true" />
          <span>Protected signatory access</span>
        </div>
      </div>
    </header>

    <div class="mx-auto w-full max-w-6xl px-5 py-8 sm:px-8 sm:py-12">
      <nav class="mx-auto mb-8 max-w-xl" aria-label="Payment steps">
        <ol
          class="grid grid-cols-3 gap-2 border-y border-outline-gray-2 py-4 text-xs"
        >
          <li
            v-for="step in checkoutSteps"
            :key="step.key"
            class="flex items-center gap-2"
            :class="[
              stepStatus(step.key) === 'done'
                ? 'font-medium text-ink-green-8'
                : stepStatus(step.key) === 'active'
                  ? 'font-semibold text-ink-gray-9'
                  : 'text-ink-gray-5',
            ]"
          >
            <span
              class="flex size-6 shrink-0 items-center justify-center rounded-full border text-[11px] font-bold"
              :class="[
                stepStatus(step.key) === 'done'
                  ? 'border-green-200 bg-green-50 text-green-700'
                  : stepStatus(step.key) === 'active'
                    ? 'border-ink-gray-8 bg-ink-gray-9 text-white'
                    : 'border-outline-gray-3 bg-surface-white text-ink-gray-5',
              ]"
              aria-hidden="true"
            >
              {{ stepStatus(step.key) === 'done' ? '✓' : step.index }}
            </span>
            <span>{{ step.label }}</span>
          </li>
        </ol>
      </nav>

      <section v-if="!sessionToken && !otpSent" class="mx-auto max-w-xl">
        <p
          class="text-xs font-semibold uppercase tracking-[0.16em] text-ink-gray-5"
        >
          Invoice payment
        </p>
        <h1 class="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
          Review and pay your invoice securely.
        </h1>
        <p class="mt-3 max-w-lg text-base leading-7 text-ink-gray-6">
          Enter the OIS reference from your invitation. We’ll send a one-time
          code to the facility signatory before showing payment details.
        </p>

        <form
          class="border border-outline-gray-2 bg-surface-white p-5 shadow-sm sm:p-7"
          @submit.prevent="requestOtp"
        >
          <div class="flex items-start gap-3">
            <span
              class="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-surface-gray-2 text-xs font-semibold text-ink-gray-6"
              aria-hidden="true"
              >1</span
            >
            <div>
              <h2 class="text-base font-semibold">Find your payment record</h2>
              <p class="mt-1 text-sm leading-5 text-ink-gray-6">
                Your reference begins with
                <span class="font-medium text-ink-gray-7">OIS-</span>.
              </p>
            </div>
          </div>
          <label
            class="mt-6 block text-sm font-medium text-ink-gray-8"
            for="ois-number"
          >
            OIS reference
          </label>
          <input
            id="ois-number"
            v-model="oisNumber"
            class="mt-2 w-full rounded-lg border border-outline-gray-3 bg-surface-white px-3 py-3 font-mono text-base uppercase outline-none transition focus:border-ink-gray-7 focus:ring-2 focus:ring-ink-gray-3"
            placeholder="OIS-2026-00001"
            autocomplete="off"
            autocapitalize="characters"
            spellcheck="false"
          />
          <p class="mt-2 text-xs leading-5 text-ink-gray-5">
            We only use this to locate the protected payment record. No invoice
            details are shown until the signatory code is verified.
          </p>
          <p
            v-if="errorMessage"
            class="mt-4 rounded-lg border border-outline-red-2 bg-surface-red-1 px-3 py-2.5 text-sm text-ink-red-7"
            role="alert"
          >
            {{ errorMessage }}
          </p>
          <button
            type="submit"
            class="mt-6 inline-flex w-full items-center justify-center rounded-lg bg-ink-gray-9 px-4 py-3 text-sm font-semibold text-white transition hover:bg-ink-gray-8 focus:outline-none focus:ring-2 focus:ring-ink-gray-5 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="requestingOtp || !oisNumber.trim()"
          >
            <span
              v-if="requestingOtp"
              class="mr-2 size-4 animate-spin rounded-full border-2 border-white/40 border-t-white"
              aria-hidden="true"
            />
            {{
              requestingOtp
                ? 'Sending secure code…'
                : 'Continue to verification'
            }}
          </button>
        </form>
      </section>

      <section
        v-else-if="
          !sessionToken && otpSent && !verifyingOtp && !checkoutLoading
        "
        class="mx-auto max-w-xl"
      >
        <button
          type="button"
          class="text-sm font-medium text-ink-gray-6 underline underline-offset-4 hover:text-ink-gray-9"
          @click="reset"
        >
          ← Use a different reference
        </button>
        <div
          class="mt-6 border border-outline-gray-2 bg-surface-white p-5 shadow-sm sm:p-7"
        >
          <div class="flex items-start justify-between gap-4">
            <div class="flex items-start gap-3">
              <span
                class="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-green-50 text-sm font-bold text-green-700"
                aria-hidden="true"
                >✓</span
              >
              <div>
                <p
                  class="text-xs font-semibold uppercase tracking-[0.14em] text-ink-gray-5"
                >
                  Step 2 of 3
                </p>
                <h1 class="mt-1 text-2xl font-semibold tracking-tight">
                  Check the signatory’s inbox
                </h1>
              </div>
            </div>
            <span
              class="rounded-full bg-surface-gray-2 px-2.5 py-1 font-mono text-xs text-ink-gray-6"
            >
              {{ oisNumber }}
            </span>
          </div>

          <p class="mt-5 text-sm leading-6 text-ink-gray-6">
            Enter the six-digit code we sent to the saved facility signatory. It
            expires after 10 minutes.
          </p>
          <p class="sr-only" aria-live="polite">{{ otpStatusMessage }}</p>

          <form class="mt-6" @submit.prevent="verifyOtp">
            <label
              class="block text-sm font-medium text-ink-gray-8"
              for="payment-otp"
            >
              Verification code
            </label>
            <input
              id="payment-otp"
              v-model="otp"
              class="mt-2 w-full rounded-lg border border-outline-gray-3 px-3 py-3 text-center font-mono text-2xl font-semibold tracking-[0.38em] outline-none transition placeholder:tracking-[0.38em] focus:border-ink-gray-7 focus:ring-2 focus:ring-ink-gray-3"
              inputmode="numeric"
              pattern="[0-9]*"
              maxlength="6"
              autocomplete="one-time-code"
              placeholder="000000"
              :disabled="verifyingOtp"
              :aria-busy="verifyingOtp"
              @input="sanitizeOtp"
            />
            <p
              class="mt-3 text-center text-xs text-ink-gray-5"
              :class="otpExpiresIn === 0 ? 'text-ink-red-6' : ''"
            >
              <template v-if="otpExpiresIn > 0">
                Code expires in {{ formatCountdown(otpExpiresIn) }}
              </template>
              <template v-else>Code expired. Request a new code.</template>
            </p>
            <p
              v-if="errorMessage"
              class="mt-4 rounded-lg border border-outline-red-2 bg-surface-red-1 px-3 py-2.5 text-sm text-ink-red-7"
              role="alert"
            >
              {{ errorMessage }}
            </p>
            <button
              type="submit"
              class="mt-5 inline-flex w-full items-center justify-center rounded-lg bg-ink-gray-9 px-4 py-3 text-sm font-semibold text-white transition hover:bg-ink-gray-8 focus:outline-none focus:ring-2 focus:ring-ink-gray-5 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="verifyingOtp || otp.length < 6 || otpExpiresIn === 0"
            >
              <span
                v-if="verifyingOtp"
                class="mr-2 size-4 animate-spin rounded-full border-2 border-white/40 border-t-white"
                aria-hidden="true"
              />
              {{ verifyingOtp ? 'Verifying securely…' : 'View invoices' }}
            </button>
          </form>

          <div class="mt-6 border-t border-outline-gray-2 pt-4 text-sm">
            <p class="text-ink-gray-6">Didn’t receive a code?</p>
            <button
              type="button"
              class="mt-1 font-medium text-ink-gray-8 underline underline-offset-4 hover:text-ink-gray-6 disabled:cursor-not-allowed disabled:text-ink-gray-4 disabled:no-underline"
              :disabled="requestingOtp || resendIn > 0"
              @click="requestOtp"
            >
              <template v-if="resendIn > 0"
                >Request another code in {{ resendIn }}s</template
              >
              <template v-else>
                <span
                  v-if="requestingOtp"
                  class="mr-1 inline-block size-3 animate-spin rounded-full border border-ink-gray-3 border-t-ink-gray-8 align-[-1px]"
                  aria-hidden="true"
                />
                {{ requestingOtp ? 'Sending code…' : 'Request another code' }}
              </template>
            </button>
          </div>
        </div>
      </section>

      <section
        v-else-if="verifyingOtp || checkoutLoading"
        class="mx-auto max-w-xl"
        aria-live="polite"
        aria-busy="true"
      >
        <div
          class="border border-outline-gray-2 bg-surface-white px-6 py-12 text-center shadow-sm sm:px-10"
        >
          <div
            class="mx-auto flex size-14 items-center justify-center rounded-full bg-surface-gray-2"
            aria-hidden="true"
          >
            <span
              class="size-7 animate-spin rounded-full border-2 border-outline-gray-3 border-t-ink-gray-8"
            />
          </div>
          <p
            class="mt-6 text-xs font-semibold uppercase tracking-[0.14em] text-ink-gray-5"
          >
            {{ verifyingOtp ? 'Step 2 of 3' : 'Step 3 of 3' }}
          </p>
          <h1 class="mt-2 text-2xl font-semibold tracking-tight">
            {{ verifyingOtp ? 'Verifying your code' : 'Loading your invoices' }}
          </h1>
          <p class="mx-auto mt-3 max-w-md text-sm leading-6 text-ink-gray-6">
            {{
              verifyingOtp
                ? 'We’re checking the code and unlocking your protected payment record.'
                : 'Your secure payment session is ready. We’re loading the latest invoice details.'
            }}
          </p>
          <div
            class="mx-auto mt-7 h-1.5 max-w-xs overflow-hidden rounded-full bg-surface-gray-2"
          >
            <div
              class="h-full w-2/3 animate-pulse rounded-full bg-ink-gray-8"
            />
          </div>
          <p class="mt-3 text-xs text-ink-gray-5">
            Please keep this window open.
          </p>
        </div>
      </section>

      <section v-else>
        <div
          class="flex flex-wrap items-end justify-between gap-4 border-b border-outline-gray-2 pb-6"
        >
          <div>
            <p
              class="text-xs font-semibold uppercase tracking-[0.16em] text-ink-gray-5"
            >
              Secure checkout · {{ oisNumber }}
            </p>
            <h1 class="mt-2 text-3xl font-semibold tracking-tight">
              Invoices ready for payment
            </h1>
            <p class="mt-2 max-w-2xl text-sm leading-6 text-ink-gray-6">
              Choose an invoice and a payment method. Online payments are
              confirmed before your invoice is marked paid.
            </p>
          </div>
          <button
            type="button"
            class="text-sm font-medium text-ink-gray-6 underline underline-offset-4 hover:text-ink-gray-9"
            @click="reset"
          >
            Use another reference
          </button>
        </div>

        <div
          v-if="callbackMessage"
          class="mt-6 rounded-lg border border-outline-green-2 bg-surface-green-1 px-4 py-3 text-sm text-ink-green-8"
          role="status"
        >
          {{ callbackMessage }}
        </div>
        <div
          v-if="errorMessage"
          class="mt-6 rounded-lg border border-outline-red-2 bg-surface-red-1 px-4 py-3 text-sm text-ink-red-7"
          role="alert"
        >
          {{ errorMessage }}
        </div>

        <div
          v-if="!invoices.length"
          class="mt-8 border border-outline-gray-2 bg-surface-white px-6 py-10 text-center shadow-sm sm:px-10"
        >
          <span
            class="mx-auto flex size-10 items-center justify-center rounded-full bg-surface-gray-2 text-lg text-ink-gray-5"
            aria-hidden="true"
            >✓</span
          >
          <h2 class="mt-4 text-lg font-semibold">Nothing to pay yet</h2>
          <p class="mx-auto mt-2 max-w-md text-sm leading-6 text-ink-gray-6">
            There is no submitted invoice ready for payment at the moment. Keep
            this link—payment options will appear here as soon as an invoice is
            issued.
          </p>
        </div>

        <div
          v-else
          class="mt-8 overflow-hidden border border-outline-gray-2 bg-surface-white shadow-sm"
        >
          <div
            class="border-b border-outline-gray-2 bg-surface-gray-1 px-5 py-3 text-sm text-ink-gray-6"
          >
            {{ invoices.length }}
            {{ invoices.length === 1 ? 'invoice' : 'invoices' }} outstanding
          </div>
          <article
            v-for="invoice in invoices"
            :key="invoice.name"
            class="border-b border-outline-gray-2 px-5 py-5 last:border-b-0 sm:px-6"
          >
            <div
              class="flex flex-col justify-between gap-5 md:flex-row md:items-center"
            >
              <div>
                <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <h2 class="font-mono text-sm font-semibold text-ink-gray-8">
                    {{ invoice.invoice_number }}
                  </h2>
                  <span
                    class="rounded-full bg-surface-amber-1 px-2 py-0.5 text-xs font-medium text-ink-amber-8"
                  >
                    Outstanding
                  </span>
                </div>
                <p class="mt-2 text-sm text-ink-gray-6">
                  Due
                  <span class="font-medium text-ink-gray-7">{{
                    humanDate(invoice.due_date)
                  }}</span>
                </p>
              </div>
              <div class="md:text-right">
                <p
                  class="text-xs font-medium uppercase tracking-wide text-ink-gray-5"
                >
                  Amount due
                </p>
                <p class="mt-1 text-2xl font-semibold tabular-nums">
                  {{ formatMoney(invoice.amount, invoice.currency) }}
                </p>
              </div>
            </div>

            <div class="mt-5 flex flex-col gap-2 sm:flex-row sm:items-center">
              <button
                v-if="paystack.enabled"
                type="button"
                class="inline-flex items-center justify-center rounded-lg bg-ink-gray-9 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-ink-gray-8 disabled:cursor-not-allowed disabled:opacity-50"
                :disabled="Boolean(paying)"
                @click="payWithPaystack(invoice)"
              >
                <span
                  v-if="paying === invoice.name"
                  class="mr-2 size-4 animate-spin rounded-full border-2 border-white/40 border-t-white"
                  aria-hidden="true"
                />
                {{
                  paying === invoice.name
                    ? 'Opening secure payment…'
                    : 'Pay online'
                }}
              </button>
              <button
                type="button"
                class="inline-flex justify-center rounded-lg border border-outline-gray-3 px-4 py-2.5 text-sm font-semibold text-ink-gray-7 transition hover:bg-surface-gray-1"
                @click="openTransfer(invoice)"
              >
                {{
                  transferInvoice?.name === invoice.name
                    ? 'Close bank transfer'
                    : 'Pay by bank transfer'
                }}
              </button>
              <p class="text-xs leading-5 text-ink-gray-5 sm:ml-1">
                {{
                  paystack.enabled
                    ? 'Online payment is processed securely.'
                    : 'Online payment is unavailable; use bank transfer.'
                }}
              </p>
            </div>

            <div
              v-if="transferInvoice?.name === invoice.name"
              class="mt-5 border-l-2 border-ink-gray-7 bg-surface-gray-1 p-4 sm:p-5"
            >
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 class="text-sm font-semibold">Bank transfer details</h3>
                  <p class="mt-1 text-sm text-ink-gray-6">
                    Transfer the exact invoice amount, then share the bank
                    reference below.
                  </p>
                </div>
                <span class="font-semibold tabular-nums text-ink-gray-8">{{
                  formatMoney(invoice.amount, invoice.currency)
                }}</span>
              </div>
              <dl class="mt-5 grid gap-3 text-sm sm:grid-cols-3">
                <div>
                  <dt
                    class="text-xs font-medium uppercase tracking-wide text-ink-gray-5"
                  >
                    Bank
                  </dt>
                  <dd class="mt-1 font-medium">{{ bankDetails.bank }}</dd>
                </div>
                <div>
                  <dt
                    class="text-xs font-medium uppercase tracking-wide text-ink-gray-5"
                  >
                    Account name
                  </dt>
                  <dd class="mt-1 font-medium">
                    {{ bankDetails.account_name }}
                  </dd>
                </div>
                <div>
                  <dt
                    class="text-xs font-medium uppercase tracking-wide text-ink-gray-5"
                  >
                    Account number
                  </dt>
                  <dd class="mt-1 font-medium">
                    {{ bankDetails.account_number }}
                  </dd>
                </div>
              </dl>
              <form
                class="mt-5 flex flex-col gap-3 sm:flex-row"
                @submit.prevent="reportTransfer(invoice)"
              >
                <label
                  class="sr-only"
                  :for="`transfer-reference-${invoice.name}`"
                  >Bank transfer reference</label
                >
                <input
                  :id="`transfer-reference-${invoice.name}`"
                  v-model="transferReference"
                  class="min-w-0 flex-1 rounded-lg border border-outline-gray-3 bg-surface-white px-3 py-2.5 text-sm outline-none focus:border-ink-gray-7 focus:ring-2 focus:ring-ink-gray-3"
                  placeholder="Bank transfer reference"
                />
                <button
                  type="submit"
                  class="inline-flex items-center justify-center rounded-lg bg-ink-gray-9 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-ink-gray-8 disabled:cursor-not-allowed disabled:opacity-50"
                  :disabled="reportingTransfer || !transferReference.trim()"
                >
                  <span
                    v-if="reportingTransfer"
                    class="mr-2 size-4 animate-spin rounded-full border-2 border-white/40 border-t-white"
                    aria-hidden="true"
                  />
                  {{
                    reportingTransfer
                      ? 'Submitting…'
                      : 'Submit for reconciliation'
                  }}
                </button>
              </form>
              <p class="mt-3 text-xs leading-5 text-ink-gray-5">
                Finance will reconcile your transfer before marking this invoice
                paid.
              </p>
            </div>
          </article>
        </div>

        <p class="mt-6 text-xs leading-5 text-ink-gray-5">
          Your payment session is private to this browser and expires
          automatically.
        </p>
      </section>
    </div>
  </main>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { createResource } from 'frappe-ui'

const OTP_RESEND_COOLDOWN_SECONDS = 60
const OTP_EXPIRES_SECONDS = 10 * 60
const checkoutSteps = [
  { key: 'reference', label: 'Reference', index: 1 },
  { key: 'verify', label: 'Verify', index: 2 },
  { key: 'pay', label: 'Pay', index: 3 },
]

const props = defineProps({ initialOis: { type: String, default: '' } })
const oisNumber = ref(
  props.initialOis ||
    new URLSearchParams(window.location.search).get('ois') ||
    '',
)
const otp = ref('')
const otpSent = ref(false)
const sessionToken = ref('')
const checkout = ref(null)
const requestingOtp = ref(false)
const verifyingOtp = ref(false)
const checkoutLoading = ref(false)
const reportingTransfer = ref(false)
const paying = ref('')
const errorMessage = ref('')
const callbackMessage = ref('')
const otpStatusMessage = ref('')
const resendIn = ref(0)
const otpExpiresIn = ref(0)
const transferInvoice = ref(null)
const transferReference = ref('')

let resendTimer
let otpExpiryTimer

const requestOtpResource = createResource({
  url: 'crm.api.checkout.request_payment_otp',
})
const verifyOtpResource = createResource({
  url: 'crm.api.checkout.verify_payment_otp',
})
const checkoutResource = createResource({
  url: 'crm.api.checkout.get_payment_checkout',
})
const paystackResource = createResource({
  url: 'crm.api.checkout.initialize_paystack_payment',
})
const verifyPaystackResource = createResource({
  url: 'crm.api.checkout.verify_paystack_payment',
})
const transferResource = createResource({
  url: 'crm.api.checkout.report_bank_transfer',
})

const network = computed(() => checkout.value?.network || {})
const invoices = computed(() => checkout.value?.invoices || [])
const bankDetails = computed(() => checkout.value?.bank_details || {})
const paystack = computed(() => checkout.value?.paystack || { enabled: false })
const brandName = computed(() => network.value.display_name || 'CareverseHIMS')
const brandColor = computed(() => {
  const colour = network.value.primary_colour
  return /^#[0-9a-f]{6}$/i.test(colour || '') ? colour : '#b91c1c'
})

const checkoutStage = computed(() => {
  if (sessionToken.value && !verifyingOtp.value) return 'pay'
  return otpSent.value ? 'verify' : 'reference'
})

function stepStatus(stepKey) {
  const order = { reference: 0, verify: 1, pay: 2 }
  const current = order[checkoutStage.value]
  const step = order[stepKey]
  if (step < current) return 'done'
  if (step === current) return 'active'
  return 'pending'
}

function friendlyError(error) {
  return (
    error?.messages?.[0] ||
    error?.message ||
    'We could not complete that request. Please try again.'
  )
}

function startResendCountdown() {
  window.clearInterval(resendTimer)
  resendIn.value = OTP_RESEND_COOLDOWN_SECONDS
  resendTimer = window.setInterval(() => {
    resendIn.value = Math.max(resendIn.value - 1, 0)
    if (!resendIn.value) window.clearInterval(resendTimer)
  }, 1000)
}

function startOtpExpiryCountdown() {
  window.clearInterval(otpExpiryTimer)
  otpExpiresIn.value = OTP_EXPIRES_SECONDS
  otpExpiryTimer = window.setInterval(() => {
    otpExpiresIn.value = Math.max(otpExpiresIn.value - 1, 0)
    if (!otpExpiresIn.value) window.clearInterval(otpExpiryTimer)
  }, 1000)
}

function formatCountdown(seconds) {
  const minutes = Math.floor(seconds / 60)
  const remainder = seconds % 60
  return minutes + ':' + String(remainder).padStart(2, '0')
}

function sanitizeOtp() {
  otp.value = otp.value.replace(/\D/g, '').slice(0, 6)
  errorMessage.value = ''
}

async function requestOtp() {
  if (
    !oisNumber.value.trim() ||
    requestingOtp.value ||
    (otpSent.value && resendIn.value > 0)
  )
    return

  requestingOtp.value = true
  errorMessage.value = ''
  try {
    await requestOtpResource.submit({ ois_number: oisNumber.value.trim() })
    otp.value = ''
    otpSent.value = true
    otpStatusMessage.value = 'A verification code was requested.'
    startResendCountdown()
    startOtpExpiryCountdown()
    await nextTick()
    document.getElementById('payment-otp')?.focus()
  } catch (error) {
    errorMessage.value = friendlyError(error)
  } finally {
    requestingOtp.value = false
  }
}

async function verifyOtp() {
  if (verifyingOtp.value || otp.value.length < 6) return
  if (!otpExpiresIn.value) {
    errorMessage.value =
      'This code has expired. Request a new code to continue.'
    return
  }

  verifyingOtp.value = true
  errorMessage.value = ''
  try {
    const result = await verifyOtpResource.submit({
      ois_number: oisNumber.value.trim(),
      otp: otp.value,
    })
    sessionToken.value = result.session_token
    sessionStorage.setItem(
      `crm-checkout:${oisNumber.value.trim()}`,
      sessionToken.value,
    )
    checkout.value = result
    await loadCheckout({ showLoading: true })
  } catch (error) {
    sessionStorage.removeItem('crm-checkout:' + oisNumber.value.trim())
    sessionToken.value = ''
    checkout.value = null
    errorMessage.value = friendlyError(error)
  } finally {
    verifyingOtp.value = false
  }
}

async function loadCheckout({ showLoading = false } = {}) {
  if (showLoading) checkoutLoading.value = true
  try {
    const result = await checkoutResource.submit({
      session_token: sessionToken.value,
    })
    checkout.value = result
    const reference = new URLSearchParams(window.location.search).get(
      'reference',
    )
    if (reference) {
      const payment = await verifyPaystackResource.submit({
        session_token: sessionToken.value,
        reference,
      })
      callbackMessage.value = payment.paid
        ? `Payment received for ${payment.invoice}.`
        : 'Payment is still being confirmed. Refresh shortly.'
    }
  } finally {
    if (showLoading) checkoutLoading.value = false
  }
}

async function payWithPaystack(invoice) {
  if (paying.value) return

  paying.value = invoice.name
  errorMessage.value = ''
  try {
    const result = await paystackResource.submit({
      session_token: sessionToken.value,
      invoice: invoice.name,
    })
    window.location.href = result.authorization_url
  } catch (error) {
    errorMessage.value = friendlyError(error)
  } finally {
    paying.value = ''
  }
}

function openTransfer(invoice) {
  transferInvoice.value =
    transferInvoice.value?.name === invoice.name ? null : invoice
  transferReference.value = ''
  errorMessage.value = ''
}

async function reportTransfer(invoice) {
  if (reportingTransfer.value || !transferReference.value.trim()) return

  reportingTransfer.value = true
  errorMessage.value = ''
  try {
    await transferResource.submit({
      session_token: sessionToken.value,
      invoice: invoice.name,
      reference_no: transferReference.value.trim(),
    })
    callbackMessage.value =
      'Transfer submitted for finance reconciliation. The invoice will be marked paid after confirmation.'
    transferInvoice.value = null
    transferReference.value = ''
    await loadCheckout()
  } catch (error) {
    errorMessage.value = friendlyError(error)
  } finally {
    reportingTransfer.value = false
  }
}

function reset() {
  sessionStorage.removeItem(`crm-checkout:${oisNumber.value.trim()}`)
  window.clearInterval(resendTimer)
  window.clearInterval(otpExpiryTimer)
  sessionToken.value = ''
  otpSent.value = false
  checkout.value = null
  otp.value = ''
  errorMessage.value = ''
  callbackMessage.value = ''
  otpStatusMessage.value = ''
  resendIn.value = 0
  otpExpiresIn.value = 0
  transferInvoice.value = null
  transferReference.value = ''
}

function formatMoney(value, currency) {
  return `${currency || 'KES'} ${Number(value || 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

function humanDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      })
}

onMounted(async () => {
  const saved = sessionStorage.getItem(`crm-checkout:${oisNumber.value.trim()}`)
  if (!saved || !oisNumber.value.trim()) return
  sessionToken.value = saved
  checkoutLoading.value = true
  try {
    await loadCheckout()
  } catch {
    sessionStorage.removeItem(`crm-checkout:${oisNumber.value.trim()}`)
    sessionToken.value = ''
  } finally {
    checkoutLoading.value = false
  }
})

onBeforeUnmount(() => {
  window.clearInterval(resendTimer)
  window.clearInterval(otpExpiryTimer)
})
</script>
