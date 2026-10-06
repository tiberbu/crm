<template>
  <main class="min-h-screen bg-surface-gray-1 text-ink-gray-9">
    <header class="border-b border-outline-gray-2 bg-surface-white">
      <div
        class="mx-auto flex max-w-6xl items-center justify-between px-5 py-4 sm:px-8"
      >
        <div>
          <p class="text-base font-semibold tracking-tight">tiberbu Express</p>
          <p class="text-xs text-ink-gray-5">Facility onboarding</p>
        </div>
        <a
          v-if="supportEmail"
          :href="`mailto:${supportEmail}`"
          class="text-sm text-ink-gray-6 hover:text-ink-gray-9"
          >{{ __('Need help?') }}</a
        >
      </div>
    </header>
    <div class="mx-auto max-w-6xl px-5 py-8 sm:px-8 sm:py-12">
      <section
        v-if="stage === 'welcome'"
        class="grid gap-10 lg:grid-cols-[1.08fr_.92fr] lg:items-center"
      >
        <div>
          <p
            class="text-xs font-semibold uppercase tracking-[.16em] text-ink-gray-5"
          >
            {{ __('Join your network') }}
          </p>
          <h1
            class="mt-4 max-w-2xl text-4xl font-semibold leading-tight tracking-tight sm:text-6xl"
          >
            {{
              networkName
                ? `Bring ${facilityName || 'your facility'} to ${networkName}.`
                : __('Bring your facility into the right network.')
            }}
          </h1>
          <p
            class="mt-5 max-w-xl text-base leading-7 text-ink-gray-6 sm:text-lg"
          >
            {{
              __(
                'Verify your facility ownership, choose a token package, review the Opt-In terms, and receive your signing and Customer Experience access by email.',
              )
            }}
          </p>
          <button
            class="mt-8 inline-flex min-h-12 items-center rounded-xl bg-[#bc1823] px-6 text-sm font-semibold text-white shadow-lg transition hover:bg-[#8f111b]"
            @click="stage = 'identity'"
          >
            {{ __('Start secure onboarding')
            }}<span class="ml-3 text-lg">→</span>
          </button>
          <p class="mt-4 text-xs text-ink-gray-5">
            {{ __('Usually 5–10 minutes · all displayed prices exclude VAT') }}
          </p>
        </div>
        <aside
          class="rounded-2xl border border-outline-gray-2 bg-surface-white p-6 shadow-xl shadow-black/5 sm:p-8"
        >
          <p
            class="text-xs font-semibold uppercase tracking-[.15em] text-ink-gray-5"
          >
            {{ __('What happens next') }}
          </p>
          <ol class="mt-6 space-y-5">
            <li
              v-for="(item, index) in journey"
              :key="item.title"
              class="flex gap-4"
            >
              <span
                class="flex size-8 shrink-0 items-center justify-center rounded-full bg-[#fdf2f3] text-sm font-semibold text-[#bc1823]"
                >{{ index + 1 }}</span
              ><span
                ><strong class="block text-sm">{{ item.title }}</strong
                ><span class="mt-1 block text-sm leading-6 text-ink-gray-5">{{
                  item.description
                }}</span></span
              >
            </li>
          </ol>
          <p
            class="mt-7 rounded-xl bg-surface-gray-1 px-4 py-3 text-xs leading-5 text-ink-gray-6"
          >
            {{
              __(
                'Your identity and facility details are checked through the registry. We do not reveal whether an ID exists until the verification step succeeds.',
              )
            }}
          </p>
        </aside>
      </section>
      <section v-else class="mx-auto max-w-3xl">
        <div class="mb-8 flex items-center justify-between gap-4">
          <div>
            <p
              class="text-xs font-semibold uppercase tracking-[.15em] text-ink-gray-5"
            >
              {{ __('Facility onboarding') }}
            </p>
            <h1 class="mt-2 text-3xl font-semibold tracking-tight">
              {{ stageTitle }}
            </h1>
          </div>
          <button
            v-if="stage !== 'success'"
            class="text-sm text-ink-gray-5 underline underline-offset-4"
            @click="reset"
          >
            {{ __('Start over') }}
          </button>
        </div>
        <ol
          v-if="stage !== 'success'"
          class="mb-8 grid grid-cols-4 gap-2"
          aria-label="Onboarding steps"
        >
          <li
            v-for="item in progressSteps"
            :key="item.key"
            class="text-xs"
            :class="
              stepIndex(item.key) <= stepIndex(stage)
                ? 'text-[#bc1823]'
                : 'text-ink-gray-5'
            "
          >
            <span
              class="mb-2 block h-1 rounded-full"
              :class="
                stepIndex(item.key) <= stepIndex(stage)
                  ? 'bg-[#bc1823]'
                  : 'bg-surface-gray-3'
              "
            />{{ item.label }}
          </li>
        </ol>
        <div
          v-if="errorMessage"
          class="mb-5 rounded-xl border border-outline-red-2 bg-surface-red-1 px-4 py-3 text-sm text-ink-red-7"
          role="alert"
        >
          {{ errorMessage }}
        </div>
        <form
          v-if="stage === 'identity'"
          class="rounded-2xl border border-outline-gray-2 bg-surface-white p-6 shadow-sm sm:p-8"
          @submit.prevent="startIdentity"
        >
          <p class="text-sm leading-6 text-ink-gray-6">
            {{
              __(
                'Enter the ID used to register as the facility owner. We will find the facilities associated with it in the Client Registry and Health Facility Registry.',
              )
            }}
          </p>
          <label class="mt-7 block text-sm font-medium"
            >{{ __('Identification type')
            }}<select
              v-model="identityType"
              class="mt-2 block w-full rounded-lg border border-outline-gray-2 bg-surface-white px-3 py-3 text-sm"
            >
              <option value="national_id">{{ __('National ID') }}</option>
              <option value="passport">{{ __('Passport') }}</option>
              <option value="foreigner_id">{{ __('Foreigner ID') }}</option>
              <option value="alien_id">{{ __('Alien ID') }}</option>
            </select></label
          >
          <label class="mt-5 block text-sm font-medium"
            >{{ __('Identification number')
            }}<input
              v-model.trim="identityNumber"
              required
              autocomplete="off"
              class="mt-2 block w-full rounded-lg border border-outline-gray-2 px-3 py-3 text-sm"
              :placeholder="__('Enter your ID number')"
          /></label>
          <button
            :disabled="busy"
            class="mt-7 min-h-12 w-full rounded-xl bg-[#bc1823] px-5 text-sm font-semibold text-white disabled:opacity-50"
          >
            {{ busy ? __('Checking…') : __('Find my facilities') }}
          </button>
          <p class="mt-4 text-center text-xs text-ink-gray-5">
            {{
              __(
                'A one-time verification code will be sent to the contact registered against your ID.',
              )
            }}
          </p>
        </form>
        <form
          v-else-if="stage === 'otp'"
          class="rounded-2xl border border-outline-gray-2 bg-surface-white p-6 shadow-sm sm:p-8"
          @submit.prevent="verifyOtp"
        >
          <p class="text-sm leading-6 text-ink-gray-6">
            {{
              __(
                'If your details match a registered facility owner, a one-time code has been sent to the contact on file. Enter it below to continue.',
              )
            }}
          </p>
          <label class="mt-7 block text-sm font-medium"
            >{{ __('Verification code')
            }}<input
              v-model.trim="otp"
              required
              inputmode="numeric"
              maxlength="6"
              class="mt-2 block w-full rounded-lg border border-outline-gray-2 px-3 py-3 text-center text-2xl tracking-[.4em]"
              placeholder="000000" /></label
          ><button
            :disabled="busy"
            class="mt-7 min-h-12 w-full rounded-xl bg-[#bc1823] px-5 text-sm font-semibold text-white disabled:opacity-50"
          >
            {{ busy ? __('Verifying…') : __('Verify and continue') }}</button
          ><button
            type="button"
            :disabled="busy"
            class="mt-4 w-full text-sm font-medium text-[#bc1823]"
            @click="resendOtp"
          >
            {{ __('Resend code') }}
          </button>
        </form>
        <form
          v-else-if="stage === 'facilities'"
          class="space-y-5"
          @submit.prevent="continueFacilities"
        >
          <div
            class="rounded-2xl border border-outline-gray-2 bg-surface-white p-6 shadow-sm sm:p-8"
          >
            <p class="text-sm leading-6 text-ink-gray-6">
              {{
                __(
                  'Select every facility you want to onboard. Each selected facility receives its own Opt-In Request, order, and Customer Experience access mapping.',
                )
              }}
            </p>
            <div class="mt-6 space-y-3">
              <label
                v-for="facility in facilities"
                :key="facility.facility_id"
                class="flex cursor-pointer gap-4 rounded-xl border p-4"
                :class="
                  selectedFacilities.includes(facility.facility_id)
                    ? 'border-[#bc1823] bg-[#fdf2f3]'
                    : 'border-outline-gray-2'
                "
                ><input
                  v-model="selectedFacilities"
                  type="checkbox"
                  :value="facility.facility_id"
                  class="mt-1 size-4 accent-[#bc1823]"
                /><span
                  ><strong class="block text-sm">{{
                    facility.facility_name || facility.mfl_code
                  }}</strong
                  ><span class="mt-1 block text-xs text-ink-gray-5"
                    >{{ facility.facility_type || __('Facility') }} ·
                    {{
                      facility.classification || __('Classification pending')
                    }}
                    · {{ facility.mfl_code }}</span
                  ></span
                ></label
              >
            </div>
          </div>
          <button
            :disabled="!selectedFacilities.length"
            class="min-h-12 w-full rounded-xl bg-[#bc1823] px-5 text-sm font-semibold text-white disabled:opacity-50"
          >
            {{ __('Continue to pricing') }}
          </button>
        </form>
        <form
          v-else-if="stage === 'pricing'"
          class="space-y-5"
          @submit.prevent="continuePricing"
        >
          <div
            class="rounded-2xl border border-outline-gray-2 bg-surface-white p-6 shadow-sm sm:p-8"
          >
            <label class="block text-sm font-medium"
              >{{ __('Network Partner ID')
              }}<span class="ml-2 text-xs font-normal text-ink-gray-5">{{
                __('optional when a default Network is configured')
              }}</span
              ><input
                v-model.trim="partnerId"
                inputmode="numeric"
                maxlength="6"
                class="mt-2 block w-full rounded-lg border border-outline-gray-2 px-3 py-3 font-mono text-sm"
                placeholder="000000"
              /><span class="mt-2 block text-xs text-ink-gray-5">{{
                __(
                  'This six-digit ID identifies the Network configured by the CRM administrator. Leave blank to use the preconfigured Network.',
                )
              }}</span></label
            ><button
              type="button"
              :disabled="catalogBusy"
              class="mt-4 text-sm font-medium text-[#bc1823]"
              @click="loadCatalog"
            >
              {{
                catalogBusy ? __('Checking…') : __('Load Network and packages')
              }}
            </button>
          </div>
          <div
            v-if="catalog.network"
            class="rounded-2xl border border-outline-gray-2 bg-surface-white p-6 shadow-sm sm:p-8"
          >
            <p
              class="text-xs font-semibold uppercase tracking-[.15em] text-ink-gray-5"
            >
              {{ catalog.network.display_name }}
            </p>
            <h2 class="mt-2 text-xl font-semibold">
              {{ __('Choose your token package') }}
            </h2>
            <p class="mt-2 text-sm text-ink-gray-6">
              {{
                __(
                  'Token packages are global catalog items. Network-specific negotiated prices do not change this token onboarding path.',
                )
              }}
            </p>
            <div class="mt-6 grid gap-3 sm:grid-cols-2">
              <label
                v-for="item in catalog.packages"
                :key="item.item_code"
                class="cursor-pointer rounded-xl border p-4"
                :class="
                  packageCode === item.item_code
                    ? 'border-[#bc1823] bg-[#fdf2f3]'
                    : 'border-outline-gray-2'
                "
                ><input
                  v-model="packageCode"
                  type="radio"
                  :value="item.item_code"
                  class="mr-2 accent-[#bc1823]"
                /><strong class="text-sm">{{
                  item.display_name || item.item_code
                }}</strong>
                <p class="mt-2 text-sm font-semibold">
                  {{ money(item.price, item.currency) }}
                  <span class="font-normal text-ink-gray-5">{{
                    __('excl. VAT')
                  }}</span>
                </p>
                <p class="mt-2 text-xs leading-5 text-ink-gray-5">
                  {{ item.coverage_summary || item.description }}
                </p></label
              >
            </div>
          </div>
          <button
            :disabled="!catalog.network || !packageCode"
            class="min-h-12 w-full rounded-xl bg-[#bc1823] px-5 text-sm font-semibold text-white disabled:opacity-50"
          >
            {{ __('Review Opt-In and signatures') }}
          </button>
        </form>
        <form
          v-else-if="stage === 'review'"
          class="space-y-5"
          @submit.prevent="submit"
        >
          <div
            class="rounded-2xl border border-outline-gray-2 bg-surface-white p-6 shadow-sm sm:p-8"
          >
            <p class="text-sm leading-6 text-ink-gray-6">
              {{
                __(
                  'Review the facilities and token package. This creates one Opt-In Request per facility and starts the existing contract signature process.',
                )
              }}
            </p>
            <dl class="mt-6 space-y-3 text-sm">
              <div class="flex justify-between gap-4">
                <dt class="text-ink-gray-5">{{ __('Network') }}</dt>
                <dd class="font-medium">{{ catalog.network?.display_name }}</dd>
              </div>
              <div class="flex justify-between gap-4">
                <dt class="text-ink-gray-5">{{ __('Facilities') }}</dt>
                <dd class="font-medium">{{ selectedFacilities.length }}</dd>
              </div>
              <div class="flex justify-between gap-4">
                <dt class="text-ink-gray-5">{{ __('Package') }}</dt>
                <dd class="font-medium">{{ selectedPackage?.display_name }}</dd>
              </div>
            </dl>
          </div>
          <div
            class="rounded-2xl border border-outline-gray-2 bg-surface-white p-6 shadow-sm sm:p-8"
          >
            <h2 class="text-lg font-semibold">{{ __('Required witness') }}</h2>
            <p class="mt-2 text-sm text-ink-gray-6">
              {{
                __(
                  'The existing signature workflow requires all applicable network signatories and a facility witness.',
                )
              }}
            </p>
            <div class="mt-5 grid gap-4 sm:grid-cols-2">
              <input
                v-model.trim="witness.name"
                required
                class="rounded-lg border border-outline-gray-2 px-3 py-3 text-sm"
                :placeholder="__('Witness name')"
              /><input
                v-model.trim="witness.email"
                required
                type="email"
                class="rounded-lg border border-outline-gray-2 px-3 py-3 text-sm"
                :placeholder="__('Witness email')"
              /><input
                v-model.trim="witness.phone"
                class="rounded-lg border border-outline-gray-2 px-3 py-3 text-sm sm:col-span-2"
                :placeholder="__('Witness phone (optional)')"
              />
            </div>
            <label class="mt-5 flex gap-3 text-sm text-ink-gray-6"
              ><input
                v-model="termsAccepted"
                required
                type="checkbox"
                class="mt-1 accent-[#bc1823]"
              />{{
                __(
                  'I accept the Opt-In terms and authorise the signature process to begin.',
                )
              }}</label
            >
          </div>
          <button
            :disabled="busy"
            class="min-h-12 w-full rounded-xl bg-[#bc1823] px-5 text-sm font-semibold text-white disabled:opacity-50"
          >
            {{ busy ? __('Submitting…') : __('Submit facility onboarding') }}
          </button>
        </form>
        <section
          v-else
          class="rounded-2xl border border-outline-gray-2 bg-surface-white p-7 text-center shadow-sm sm:p-10"
        >
          <div
            class="mx-auto flex size-14 items-center justify-center rounded-full bg-emerald-100 text-2xl text-emerald-700"
          >
            ✓
          </div>
          <h2 class="mt-5 text-2xl font-semibold">
            {{ __('Your onboarding has started') }}
          </h2>
          <p class="mx-auto mt-3 max-w-xl text-sm leading-6 text-ink-gray-6">
            {{
              __(
                'We created a separate Opt-In Request for each facility. Check your email for the contract signature request and Customer Experience login invitation.',
              )
            }}
          </p>
          <div class="mx-auto mt-7 max-w-xl space-y-2 text-left">
            <div
              v-for="item in submissions"
              :key="item.submission"
              class="flex justify-between gap-4 rounded-lg bg-surface-gray-1 px-4 py-3 text-sm"
            >
              <span>{{ item.facility }}</span
              ><strong class="font-mono text-xs">{{ item.submission }}</strong>
            </div>
          </div>
          <a
            href="/login"
            class="mt-8 inline-flex min-h-11 items-center rounded-xl bg-[#bc1823] px-5 text-sm font-semibold text-white"
            >{{ __('Go to sign in') }}</a
          >
        </section>
      </section>
    </div>
  </main>
</template>

<script setup>
import { computed, ref } from 'vue'
import { call } from 'frappe-ui'

const props = defineProps({
  networkSlug: { type: String, default: '' },
  facilityName: { type: String, default: '' },
  invitationToken: { type: String, default: '' },
})
const stage = ref('welcome')
const busy = ref(false)
const catalogBusy = ref(false)
const errorMessage = ref('')
const sessionToken = ref('')
const identityType = ref('national_id')
const identityNumber = ref('')
const identityPreview = ref({})
const otp = ref('')
const facilities = ref([])
const selectedFacilities = ref([])
const partnerId = ref('')
const catalog = ref({ network: null, packages: [] })
const packageCode = ref('')
const witness = ref({ name: '', email: '', phone: '' })
const termsAccepted = ref(false)
const submissions = ref([])
const networkName = computed(() => catalog.value.network?.display_name || '')
const supportEmail = computed(() => catalog.value.network?.contact_email || '')
const selectedPackage = computed(() =>
  catalog.value.packages.find((item) => item.item_code === packageCode.value),
)
const stageTitle = computed(
  () =>
    ({
      identity: __('Verify your identity'),
      otp: __('Confirm your contact'),
      facilities: __('Choose facilities'),
      pricing: __('Choose your package'),
      review: __('Review and submit'),
      success: __('All set'),
    })[stage.value],
)
const journey = [
  {
    title: __('Verify ownership'),
    description: __('Find your registered profile and facilities securely.'),
  },
  {
    title: __('Choose a package'),
    description: __(
      'See facility-friendly token coverage and prices excluding VAT.',
    ),
  },
  {
    title: __('Start signatures'),
    description: __(
      'Create the Opt-In Requests and send the required signature invitations.',
    ),
  },
  {
    title: __('Track progress'),
    description: __(
      'Use Customer Experience to follow implementation through GoLive.',
    ),
  },
]
const progressSteps = [
  { key: 'identity', label: __('Identity') },
  { key: 'facilities', label: __('Facilities') },
  { key: 'pricing', label: __('Package') },
  { key: 'review', label: __('Submit') },
]
function stepIndex(value) {
  return (
    { identity: 0, otp: 0, facilities: 1, pricing: 2, review: 3, success: 4 }[
      value
    ] ?? 0
  )
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
async function request(method, args) {
  return unwrap(await call(`crm.api.facility_onboarding.${method}`, args))
}
async function startIdentity() {
  errorMessage.value = ''
  busy.value = true
  try {
    const data = await request('start_identity', {
      identification_type: identityType.value,
      identification_number: identityNumber.value,
    })
    sessionToken.value = data.session_token
    identityPreview.value = data.identity || {}
    stage.value = 'otp'
  } catch (error) {
    errorMessage.value =
      error?.messages?.[0] ||
      __('We could not verify those details. Please try again.')
  } finally {
    busy.value = false
  }
}
async function resendOtp() {
  errorMessage.value = ''
  try {
    await request('resend_otp', { session_token: sessionToken.value })
  } catch (error) {
    errorMessage.value =
      error?.messages?.[0] || __('We could not resend the code.')
  }
}
async function verifyOtp() {
  errorMessage.value = ''
  busy.value = true
  try {
    const data = await request('verify_otp', {
      session_token: sessionToken.value,
      otp: otp.value,
    })
    identityPreview.value = data.identity || identityPreview.value
    facilities.value = data.facilities || []
    stage.value = 'facilities'
  } catch (error) {
    errorMessage.value =
      error?.messages?.[0] || __('The code is incorrect or expired.')
  } finally {
    busy.value = false
  }
}
function continueFacilities() {
  if (selectedFacilities.value.length) stage.value = 'pricing'
}
async function loadCatalog() {
  errorMessage.value = ''
  catalogBusy.value = true
  try {
    catalog.value = await request('get_catalog', {
      partner_id: partnerId.value,
    })
    packageCode.value = catalog.value.packages?.[0]?.item_code || ''
  } catch (error) {
    catalog.value = { network: null, packages: [] }
    errorMessage.value =
      error?.messages?.[0] || __('That Partner ID is not available.')
  } finally {
    catalogBusy.value = false
  }
}
function continuePricing() {
  if (catalog.value.network && packageCode.value) stage.value = 'review'
}
async function submit() {
  errorMessage.value = ''
  busy.value = true
  try {
    const data = await request('submit_onboarding', {
      session_token: sessionToken.value,
      partner_id: partnerId.value,
      selected_facility_ids: JSON.stringify(selectedFacilities.value),
      package_item_code: packageCode.value,
      witness: JSON.stringify(witness.value),
      terms_accepted: termsAccepted.value ? 1 : 0,
    })
    submissions.value = data.submissions || []
    stage.value = 'success'
  } catch (error) {
    errorMessage.value =
      error?.messages?.[0] ||
      __('We could not complete onboarding. Please try again.')
  } finally {
    busy.value = false
  }
}
function reset() {
  stage.value = 'welcome'
  errorMessage.value = ''
  sessionToken.value = ''
  facilities.value = []
  selectedFacilities.value = []
  catalog.value = { network: null, packages: [] }
  packageCode.value = ''
}
</script>
