<template>
  <div class="min-h-screen bg-gray-50 dark:bg-gray-900">
    <!-- ------------------------------------------------------------------ -->
    <!-- OTP Screen                                                           -->
    <!-- ------------------------------------------------------------------ -->
    <div
      v-if="screen === 'otp'"
      class="flex min-h-screen items-center justify-center p-4"
    >
      <div
        class="w-full max-w-sm rounded-2xl bg-white shadow-lg dark:bg-gray-800"
      >
        <!-- Branding header -->
        <div class="px-6 pt-8 text-center">
          <div
            class="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl mx-auto"
            style="
              background-color: color-mix(
                in srgb,
                var(--brand-primary, #bc1823) 15%,
                transparent
              );
            "
          >
            <svg
              class="h-8 w-8"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.5"
              :style="{ color: 'var(--brand-primary, #bc1823)' }"
            >
              <path
                d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
              />
            </svg>
          </div>
          <h1 class="mb-1 text-xl font-bold text-gray-900 dark:text-white">
            CareverseHIMS Contract Signing
          </h1>
          <p class="mb-2 text-xs text-gray-500 dark:text-gray-400">
            Signing as: <span class="font-medium">{{ role }}</span>
          </p>
        </div>

        <ContractOtpGate
          :contract="contract"
          :role="role"
          :token="token"
          @verified="onOtpVerified"
        />
      </div>
    </div>

    <!-- ------------------------------------------------------------------ -->
    <!-- Sign Screen                                                          -->
    <!-- ------------------------------------------------------------------ -->
    <div v-else-if="screen === 'sign'" class="mx-auto max-w-3xl px-4 py-8">
      <!-- Page header -->
      <div class="mb-6 text-center">
        <div
          class="mb-3 flex h-12 w-12 items-center justify-center rounded-xl mx-auto"
          style="
            background-color: color-mix(
              in srgb,
              var(--brand-primary, #bc1823) 15%,
              transparent
            );
          "
        >
          <svg
            class="h-6 w-6"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            :style="{ color: 'var(--brand-primary, #bc1823)' }"
          >
            <path
              d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10"
            />
          </svg>
        </div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
          Review & Sign
        </h1>
        <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Please read the full contract before signing.
        </p>
      </div>

      <div class="rounded-2xl bg-white shadow-sm dark:bg-gray-800 p-6">
        <!-- Contract viewer -->
        <ContractView
          :signing-token="signingToken"
          :contract="contract"
          :role="role"
          @scrolled-to-bottom="scrolledToBottom = true"
          @loaded="onContractLoaded"
        />

        <!-- Read & authorisation checkbox -->
        <div class="mt-5 flex items-start gap-3">
          <input
            id="read-confirm"
            v-model="readConfirmed"
            type="checkbox"
            :disabled="!scrolledToBottom"
            class="mt-0.5 h-4 w-4 cursor-pointer rounded disabled:cursor-not-allowed disabled:opacity-50"
            :style="
              readConfirmed ? 'accent-color: var(--brand-primary, #bc1823)' : ''
            "
          />
          <label
            for="read-confirm"
            :class="[
              'text-sm font-medium leading-snug select-none',
              scrolledToBottom
                ? 'cursor-pointer text-gray-800 dark:text-gray-200'
                : 'cursor-not-allowed text-gray-400 dark:text-gray-600',
            ]"
          >
            I have read and I confirm I am authorised to sign this agreement
            <span class="text-red-500">*</span>
          </label>
        </div>

        <!-- Contract-wide status is deliberately adjacent to the signing pad so
             each signer can see completed signatures before acting. -->
        <section
          v-if="signingProgress.length"
          class="mt-6 rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-900/50"
          aria-label="Contract signing progress"
        >
          <div class="flex items-baseline justify-between gap-3">
            <div>
              <h2 class="text-sm font-semibold text-gray-900 dark:text-white">
                Signing progress
              </h2>
              <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                {{ signedProgressCount }} of
                {{ signingProgress.length }} signatures complete
              </p>
            </div>
            <span
              class="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-gray-600 shadow-sm dark:bg-gray-800 dark:text-gray-300"
            >
              Any order
            </span>
          </div>
          <ul class="mt-3 divide-y divide-gray-200 dark:divide-gray-700">
            <li
              v-for="(signatory, index) in signingProgress"
              :key="`${signatory.role}-${signatory.name}-${index}`"
              class="flex items-center justify-between gap-3 py-2 first:pt-0 last:pb-0"
            >
              <div class="min-w-0">
                <p
                  class="truncate text-sm font-medium text-gray-800 dark:text-gray-200"
                >
                  {{ signatory.name }}
                </p>
                <p class="truncate text-xs text-gray-500 dark:text-gray-400">
                  {{ signatory.role }}
                </p>
              </div>
              <span
                :class="[
                  'shrink-0 rounded-full px-2 py-1 text-xs font-medium',
                  signatory.status === 'Signed'
                    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
                    : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
                ]"
              >
                {{ signatory.status }}
              </span>
            </li>
          </ul>
        </section>

        <!-- Signature canvas -->
        <div class="mt-6">
          <p
            class="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-800 dark:text-gray-200"
          >
            Your Signature <span class="text-red-500">*</span>
          </p>
          <SignatureCanvas
            ref="canvasRef"
            :disabled="!readConfirmed"
            @has-signature="hasSig = $event"
          />
        </div>

        <!-- Submit button -->
        <div class="mt-6">
          <button
            :disabled="!readConfirmed || !hasSig || signing"
            class="w-full rounded-xl px-6 py-3 text-sm font-semibold text-white transition-opacity hover:opacity-90 focus:outline-none disabled:opacity-50"
            style="background-color: var(--brand-primary, #bc1823)"
            @click="handleSign"
          >
            <span v-if="signing">Submitting…</span>
            <span v-else>Confirm Signature</span>
          </button>
          <p
            v-if="signError"
            class="mt-2 text-center text-sm text-red-500 dark:text-red-400"
          >
            {{ signError }}
          </p>
        </div>
      </div>
    </div>

    <!-- ------------------------------------------------------------------ -->
    <!-- Done Screen                                                          -->
    <!-- ------------------------------------------------------------------ -->
    <div
      v-else-if="screen === 'done'"
      class="flex min-h-screen items-center justify-center p-4"
    >
      <SigningSuccess
        :signatory-name="signatoryName"
        :contract="contract"
        :contract-date="contractDate"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { createResource } from 'frappe-ui'
import { getContractSigningError } from '@/utils/contractSigningErrors'
import { collectSigningDeviceInfo } from '@/utils/signingAudit'

import ContractOtpGate from './ContractOtpGate.vue'
import ContractView from './ContractView.vue'
import SignatureCanvas from './SignatureCanvas.vue'
import SigningSuccess from './SigningSuccess.vue'

// ---------------------------------------------------------------------------
// Boot — read URL params from data attributes on the mount element
// ---------------------------------------------------------------------------
const el = document.getElementById('signing-app')
const contract = ref(el?.dataset?.contract || '')
const role = ref(el?.dataset?.role || '')
const token = ref(el?.dataset?.token || '')

// ---------------------------------------------------------------------------
// Screen state: 'otp' → 'sign' → 'done'
// ---------------------------------------------------------------------------
const screen = ref('otp')

// Data carried from OTP gate to sign screen
const signingToken = ref('')
const signatoryName = ref('')

// Data carried from ContractView to success screen
const contractDate = ref('')
const signingProgress = ref([])
const signedProgressCount = computed(
  () =>
    signingProgress.value.filter((signatory) => signatory.status === 'Signed')
      .length,
)

// Sign screen local state
const scrolledToBottom = ref(false)
const readConfirmed = ref(false)
const hasSig = ref(false)
const signing = ref(false)
const signError = ref('')
const canvasRef = ref(null)

// ---------------------------------------------------------------------------
// Resources
// ---------------------------------------------------------------------------
const signResource = createResource({ url: 'crm.api.contracts.sign' })

// ---------------------------------------------------------------------------
// Event handlers
// ---------------------------------------------------------------------------

function onOtpVerified({ signingToken: st, signatoryName: sn }) {
  signingToken.value = st
  signatoryName.value = sn
  screen.value = 'sign'
}

function onContractLoaded({
  signatoryName: sn,
  contractDate: cd,
  signingProgress: progress,
}) {
  // ContractView may provide richer name/date than OTP verify
  if (sn) signatoryName.value = sn
  if (cd) contractDate.value = cd
  signingProgress.value = Array.isArray(progress) ? progress : []
}

async function handleSign() {
  if (!readConfirmed.value || !hasSig.value || signing.value) return
  signing.value = true
  signError.value = ''

  try {
    const signatureB64 = canvasRef.value?.getSignatureDataUrl() || ''
    await signResource.fetch({
      signing_token: signingToken.value,
      contract: contract.value,
      role: role.value,
      signature_b64: signatureB64,
      device_info: JSON.stringify(collectSigningDeviceInfo()),
    })
    screen.value = 'done'
  } catch (err) {
    signError.value = getContractSigningError(err, 'sign').message
  } finally {
    signing.value = false
  }
}
</script>
