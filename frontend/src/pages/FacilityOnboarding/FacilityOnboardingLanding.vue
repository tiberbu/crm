<template>
  <main class="min-h-screen bg-surface-gray-1 text-ink-gray-9">
    <header class="border-b border-outline-gray-2 bg-surface-white">
      <div
        class="mx-auto flex max-w-6xl items-center justify-between px-5 py-4 sm:px-8"
      >
        <div>
          <p class="text-base font-semibold tracking-tight">
            Tiberbu Customer Experience
          </p>
          <p class="text-xs text-ink-gray-5">Secure facility onboarding</p>
        </div>
        <div class="flex items-center gap-4 text-sm">
          <a
            v-if="supportEmail"
            :href="`mailto:${supportEmail}`"
            class="text-ink-gray-6 hover:text-ink-gray-9"
            >{{ __('Need help?') }}</a
          >
          <a
            href="/login?redirect-to=/cx-portal"
            class="text-ink-gray-6 hover:text-ink-gray-9"
            >{{ __('Already have access? Sign in') }}</a
          >
        </div>
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
            {{ __('Start your facility journey') }}
          </p>
          <h1
            class="mt-4 max-w-2xl text-4xl font-semibold leading-tight tracking-tight sm:text-6xl"
          >
            {{
              networkName
                ? `Onboard ${facilityName || 'your facility'} with ${networkName}.`
                : __('Onboard your facility securely.')
            }}
          </h1>
          <p
            class="mt-5 max-w-xl text-base leading-7 text-ink-gray-6 sm:text-lg"
          >
            {{
              __(
                'Verify your identity, select your facilities and token package, accept the Terms, and get secure Customer Experience access.',
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
      <section
        v-if="stage === 'welcome'"
        class="mt-10 rounded-2xl border border-outline-gray-2 bg-surface-white p-6 shadow-sm sm:p-8"
        aria-labelledby="hmis-about-title"
      >
        <p
          class="text-xs font-semibold uppercase tracking-[.15em] text-ink-gray-5"
        >
          {{ __('About Tiberbu HMIS') }}
        </p>
        <h2 id="hmis-about-title" class="mt-2 text-xl font-semibold">
          {{
            __('One connected path from verification to Customer Experience')
          }}
        </h2>
        <p class="mt-3 max-w-3xl text-sm leading-6 text-ink-gray-6">
          {{
            __(
              'Tiberbu HMIS connects identity checks, facility selection, token package orders and Customer Experience access. This wizard is for facility owners and administrators.',
            )
          }}
        </p>
        <a
          href="/login?redirect-to=/crm"
          class="mt-4 inline-flex text-sm font-medium text-[#bc1823] underline underline-offset-4"
          >{{ __('Staff access') }}</a
        >
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
          :aria-label="__('Onboarding steps')"
        >
          <li
            v-for="item in progressSteps"
            :key="item.key"
            class="text-xs"
            :aria-current="item.status === 'current' ? 'step' : undefined"
            :class="
              item.status === 'upcoming' ? 'text-ink-gray-5' : 'text-[#bc1823]'
            "
          >
            <span
              class="mb-2 block h-1 rounded-full"
              :class="
                item.status === 'upcoming'
                  ? 'bg-surface-gray-3'
                  : 'bg-[#bc1823]'
              "
            />{{ item.label
            }}<span class="sr-only"> — {{ item.statusLabel }}</span>
          </li>
        </ol>
        <div
          v-if="errorMessage"
          class="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-outline-red-2 bg-surface-red-1 px-4 py-3 text-sm text-ink-red-7"
          role="alert"
        >
          <span>{{ errorMessage }}</span
          ><a
            v-if="registrationConflictDetected"
            href="/login?redirect-to=/cx-portal"
            data-testid="duplicate-signin"
            class="font-semibold underline underline-offset-4"
            >{{ __('Sign in to Customer Experience') }}</a
          ><a
            v-if="registrationConflictDetected && supportEmail"
            :href="`mailto:${supportEmail}`"
            data-testid="duplicate-support"
            class="font-semibold underline underline-offset-4"
            >{{ __('Contact support') }}</a
          ><button
            v-if="sessionExpired"
            type="button"
            class="font-semibold underline underline-offset-4"
            @click="reset"
          >
            {{ __('Start again') }}
          </button>
        </div>
        <form
          v-if="stage === 'identity'"
          class="rounded-2xl border border-outline-gray-2 bg-surface-white p-6 shadow-sm sm:p-8"
          @submit.prevent="startIdentity"
        >
          <p class="text-sm leading-6 text-ink-gray-6">
            {{
              __(
                'Enter the ID used to register as the facility owner. We will check the registered contact first and look up facility details after you verify the code.',
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
          <div
            v-if="hfrRetryPending"
            class="rounded-xl bg-surface-amber-1 px-4 py-3 text-sm leading-6 text-ink-amber-3"
            role="status"
          >
            <p>
              {{
                hfrRetryExhausted
                  ? __(
                      'We could not load facility details. Please contact support for help continuing.',
                    )
                  : __(
                      'Your contact is verified, but facility details are temporarily unavailable. Retry to continue without requesting another code.',
                    )
              }}
            </p>
            <button
              v-if="!hfrRetryExhausted"
              type="button"
              :disabled="busy"
              class="mt-3 font-semibold underline underline-offset-4 disabled:opacity-50"
              @click="retryHfr"
            >
              {{
                busy ? __('Checking facilities…') : __('Retry facility lookup')
              }}
            </button>
          </div>
          <template v-else>
            <div
              v-if="deliveryStatus === 'unavailable'"
              class="rounded-xl bg-surface-amber-1 px-4 py-3 text-sm leading-6 text-ink-amber-3"
              role="status"
            >
              {{
                __(
                  'We could not deliver a code just now. Retry delivery to this verified contact session.',
                )
              }}
            </div>
            <div v-else class="text-center" role="status">
              <p class="text-sm leading-6 text-ink-gray-6">
                {{
                  delivery.masked_destination
                    ? __('A 6-digit code was sent by {0} to {1}.', [deliveryChannelLabel, delivery.masked_destination])
                    : __('If your details match our records, a 6-digit code was sent to the registered contact.')
                }}
              </p>
              <p class="mt-2 text-xs text-ink-gray-5">
                {{ __('The code expires in {0} minutes.', [expiryMinutes]) }}
              </p>
            </div>
            <div class="mt-7">
              <OtpCodeInput
                v-model="otp"
                :disabled="busy"
                :error="otpError"
                :label="__('Verification code')"
              />
            </div>
            <button
              :disabled="busy || otp.length !== 6"
              class="mt-7 min-h-12 w-full rounded-xl bg-[#bc1823] px-5 text-sm font-semibold text-white disabled:opacity-50"
            >
              {{ busy ? __('Verifying…') : __('Verify and continue') }}</button
            ><button
              type="button"
              :disabled="!canResendOtp(delivery, resendIn, busy)"
              class="mt-4 min-h-11 w-full text-sm font-medium text-[#bc1823] disabled:text-ink-gray-4"
              @click="resendOtp"
            >
              {{
                deliveryStatus === 'unavailable'
                  ? __('Retry code delivery')
                  : resendIn > 0
                    ? __('Resend code in {0}', [formatCountdown(resendIn)])
                    : __('Resend code')
              }}
            </button>
            <button
              type="button"
              :disabled="busy"
              class="min-h-11 w-full text-sm font-medium text-ink-gray-6 disabled:text-ink-gray-4"
              @click="editIdentity"
            >
              {{ __('Edit ID details') }}
            </button>
          </template>
        </form>
        <form
          v-else-if="stage === 'facilities'"
          class="space-y-5"
          @submit.prevent="continueFacilities"
        >
          <div
            class="rounded-2xl border border-outline-gray-2 bg-surface-white p-6 shadow-sm sm:p-8"
          >
            <section
              v-if="identityPreview.full_name || identityPreview.email || identityPreview.phone"
              class="mb-6 rounded-xl bg-surface-gray-1 p-4"
              :aria-label="__('Verified identity')"
            >
              <h2 class="text-sm font-semibold">{{ __('Verified identity') }}</h2>
              <p v-if="identityPreview.full_name" class="mt-1 text-sm text-ink-gray-6">
                {{ identityPreview.full_name }}
              </p>
              <p v-if="identityPreview.email" class="mt-1 text-xs text-ink-gray-5">
                {{ __('Email: {0}', [identityPreview.email]) }}
              </p>
              <p v-if="identityPreview.phone" class="mt-1 text-xs text-ink-gray-5">
                {{ __('Phone: {0}', [identityPreview.phone]) }}
              </p>
            </section>
            <p class="text-sm leading-6 text-ink-gray-6">
              {{
                __(
                  'Select every facility you want to onboard. We will create a separate network application and token order for each facility.',
                )
              }}
            </p>
            <p
              v-if="!facilities.length"
              class="mt-5 rounded-xl bg-surface-gray-1 px-4 py-3 text-sm leading-6 text-ink-gray-6"
              role="status"
            >
              {{
                __(
                  'No eligible facilities were returned for this verified identity. Contact support if you think this is an error.',
                )
              }}
            </p>
            <div class="mt-6 space-y-3">
              <label
                v-for="facility in facilities"
                :key="facility.facility_id"
                class="flex gap-4 rounded-xl border p-4"
                :class="
                  facility.onboarding_eligible !== true
                    ? 'cursor-not-allowed border-outline-gray-2 bg-surface-gray-1 opacity-70'
                    : selectedFacilities.includes(facility.facility_id)
                      ? 'cursor-pointer border-[#bc1823] bg-[#fdf2f3]'
                      : 'cursor-pointer border-outline-gray-2'
                "
                ><input
                  v-model="selectedFacilities"
                  type="checkbox"
                  :value="facility.facility_id"
                  :disabled="facility.onboarding_eligible !== true"
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
                  ><span
                    v-if="facility.onboarding_eligible !== true"
                    class="mt-2 block text-xs font-medium text-ink-gray-6"
                    >{{
                      facility.facility_eligibility_reason === 'missing_level'
                        ? __('Unavailable for token self-onboarding because HFR did not return a Facility Level.')
                        : __('Unavailable for token self-onboarding because this Facility Level is not approved.')
                    }}</span
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
                  'Choose the token package you want for your selected facilities.',
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
                  {{ money(item.price_ex_vat ?? item.price, item.currency) }}
                  <span class="font-normal text-ink-gray-5">{{
                    __('excl. VAT')
                  }}</span>
                </p>
                <p v-if="item.gross_total" class="mt-1 text-xs text-ink-gray-5">
                  {{ item.vat_label || __('VAT') }}
                  {{ money(item.vat_amount, item.currency) }} ·
                  {{ __('Total') }} {{ money(item.gross_total, item.currency) }}
                </p>
                <p class="mt-2 text-xs leading-5 text-ink-gray-5">
                  {{ item.coverage_summary || item.description }}
                </p></label
              >
            </div>
          </div>
          <button
            :disabled="!catalog.network || !packageCode || termsBusy"
            class="min-h-12 w-full rounded-xl bg-[#bc1823] px-5 text-sm font-semibold text-white disabled:opacity-50"
          >
            {{
              termsBusy ? __('Loading Terms…') : __('Confirm your data')
            }}</button
          ><button
            type="button"
            class="min-h-11 w-full text-sm font-medium text-ink-gray-6"
            @click="goBack"
          >
            {{ __('Back to facilities') }}
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
                  'Confirm your facilities and token package, provide the email for your Customer Experience account, then accept the Terms to submit.',
                )
              }}
            </p>
            <dl class="mt-6 space-y-3 text-sm">
              <div class="flex justify-between gap-4">
                <dt class="text-ink-gray-5">{{ __('Network') }}</dt>
                <dd class="font-medium">{{ catalog.network?.display_name }}</dd>
              </div>
              <div class="flex justify-between gap-4">
                <dt class="text-ink-gray-5">
                  {{ __('Facilities') }}
                  <button
                    type="button"
                    class="ml-2 min-h-8 text-xs font-medium text-[#bc1823] underline underline-offset-4"
                    @click="stage = 'facilities'"
                  >
                    {{ __('Edit') }}
                  </button>
                </dt>
                <dd class="text-right font-medium">
                  <span
                    v-for="facility in chosenFacilities"
                    :key="facility.facility_id"
                    class="block"
                    >{{ facility.facility_name || facility.mfl_code }}</span
                  >
                </dd>
              </div>
              <div class="flex justify-between gap-4">
                <dt class="text-ink-gray-5">
                  {{ __('Package') }}
                  <button
                    type="button"
                    class="ml-2 min-h-8 text-xs font-medium text-[#bc1823] underline underline-offset-4"
                    @click="stage = 'pricing'"
                  >
                    {{ __('Edit') }}
                  </button>
                </dt>
                <dd class="font-medium">{{ selectedPackage?.display_name }}</dd>
              </div>
              <div class="flex justify-between gap-4">
                <dt class="text-ink-gray-5">
                  {{ __('Customer Experience email') }}
                </dt>
                <dd class="font-medium">
                  {{ accountEmail || __('Add below') }}
                </dd>
              </div>
            </dl>
            <dl
              v-if="totals"
              class="mt-5 space-y-2 border-t border-outline-gray-2 pt-4 text-sm"
            >
              <div class="flex justify-between gap-4">
                <dt class="text-ink-gray-5">
                  {{ __('Price excl. VAT') }} ({{ totals.count }} ×
                  {{ money(totals.perFacility.exVat, totals.currency) }})
                </dt>
                <dd class="font-medium">
                  {{ money(totals.exVat, totals.currency) }}
                </dd>
              </div>
              <div class="flex justify-between gap-4">
                <dt class="text-ink-gray-5">{{ totals.vatLabel }}</dt>
                <dd class="font-medium">
                  {{ money(totals.vat, totals.currency) }}
                </dd>
              </div>
              <div class="flex justify-between gap-4 text-base">
                <dt class="font-semibold">{{ __('Total incl. VAT') }}</dt>
                <dd class="font-semibold">
                  {{ money(totals.gross, totals.currency) }}
                </dd>
              </div>
            </dl>
          </div>
          <section
            v-if="termsSnapshot"
            class="rounded-2xl border border-outline-gray-2 bg-surface-white p-6 shadow-sm sm:p-8"
            aria-labelledby="self-onboarding-terms-title"
            data-testid="self-onboarding-terms"
          >
            <h2 id="self-onboarding-terms-title" class="text-lg font-semibold">
              {{ __('Terms and Conditions') }}
            </h2>
            <p class="mt-1 text-sm text-ink-gray-5">
              {{ termsSnapshot.document }}
            </p>
            <div
              class="prose prose-sm mt-4 max-h-96 overflow-y-auto rounded-lg border border-outline-gray-2 p-4"
              v-html="termsSnapshot.rendered_html"
            />
          </section>
          <section
            class="rounded-2xl border border-outline-gray-2 bg-surface-white p-6 shadow-sm sm:p-8"
            aria-labelledby="cx-account-title"
          >
            <h2 id="cx-account-title" class="text-lg font-semibold">
              {{ __('Set up your Customer Experience account') }}
            </h2>
            <p class="mt-2 text-sm text-ink-gray-6">
              {{
                __(
                  'We will send secure password setup or recovery instructions to this email.',
                )
              }}
            </p>
            <label class="mt-5 block text-sm font-medium">
              {{ __('Account email') }}
              <input
                v-model.trim="accountEmail"
                required
                type="email"
                autocomplete="email"
                class="mt-2 block w-full rounded-lg border border-outline-gray-2 px-3 py-3 text-sm"
                :placeholder="__('you@example.com')"
              />
            </label>
            <label class="mt-5 block text-sm font-medium">
              {{ __('Partner ID') }}
              <span class="ml-2 text-xs font-normal text-ink-gray-5">{{
                __('optional')
              }}</span>
              <input
                v-model.trim="partnerId"
                inputmode="numeric"
                maxlength="6"
                class="mt-2 block w-full rounded-lg border border-outline-gray-2 px-3 py-3 font-mono text-sm"
                placeholder="000000"
                @change="loadCatalog"
              />
              <span class="mt-2 block text-xs text-ink-gray-5">
                {{
                  __(
                    'Enter the six-digit ID once to link all selected facilities to a partner network. If you leave it blank, we will use the default network.',
                  )
                }}
              </span>
            </label>
            <label class="mt-5 flex gap-3 text-sm text-ink-gray-6"
              ><input
                v-model="termsAccepted"
                required
                :disabled="!termsSnapshot?.content_hash"
                type="checkbox"
                class="mt-1 accent-[#bc1823]"
              />{{
                __(
                  'I have reviewed and accept the displayed Terms and Conditions.',
                )
              }}</label
            >
          </section>
          <button
            :disabled="busy || !reviewReady"
            class="min-h-12 w-full rounded-xl bg-[#bc1823] px-5 text-sm font-semibold text-white disabled:opacity-50"
          >
            {{
              busy ? __('Submitting…') : __('Submit facility onboarding')
            }}</button
          ><button
            type="button"
            :disabled="busy"
            class="min-h-11 w-full text-sm font-medium text-ink-gray-6"
            @click="goBack"
          >
            {{ __('Back to package') }}
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
                'We created your customer account and linked the selected facilities to the Network. Check this email for password setup instructions, then sign in to your portal to view your facilities.',
              )
            }}
          </p>
          <div class="mx-auto mt-7 max-w-xl space-y-2 text-left">
            <div
              v-for="item in submissions"
              :key="item.mfl_code"
              class="flex justify-between gap-4 rounded-lg bg-surface-gray-1 px-4 py-3 text-sm"
            >
              <span>{{ item.facility }}</span
              ><strong class="font-mono text-xs">{{ item.mfl_code }}</strong>
            </div>
          </div>
          <a
            href="/login?redirect-to=/cx-portal"
            class="mt-8 inline-flex min-h-11 items-center rounded-xl bg-[#bc1823] px-5 text-sm font-semibold text-white"
            >{{ __('Go to sign in') }}</a
          >
        </section>
      </section>
    </div>
  </main>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { call } from 'frappe-ui'
import OtpCodeInput from '@/components/FacilityOnboarding/OtpCodeInput.vue'
import {
  STEPS,
  canAdvance,
  canResendOtp,
  deliveryState,
  formatCountdown,
  packageTotals,
  previousStage,
  shouldClearOtpAfterVerificationError,
  stepStatus,
} from '@/utils/onboardingSteps'

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
const accountEmail = ref('')
const termsAccepted = ref(false)
const termsSnapshot = ref(null)
const termsBusy = ref(false)
const submissions = ref([])
const delivery = ref({})
const resendIn = ref(0)
const otpError = ref('')
const sessionExpired = ref(false)
const registrationConflictDetected = ref(false)
const hfrRetryPending = ref(false)
const hfrRetryExhausted = ref(false)
let resendTimer = null
const deliveryStatus = computed(() => deliveryState(delivery.value))
const deliveryChannelLabel = computed(() =>
  delivery.value.channel === 'sms' ? __('text message') : __('email'),
)
const expiryMinutes = computed(() =>
  Math.max(1, Math.round((delivery.value.expires_in || 600) / 60)),
)
const chosenFacilities = computed(() =>
  facilities.value.filter((item) =>
    selectedFacilities.value.includes(item.facility_id),
  ),
)
const totals = computed(() =>
  packageTotals(selectedPackage.value, selectedFacilities.value.length),
)
const reviewReady = computed(
  () =>
    Boolean(termsSnapshot.value?.content_hash) &&
    canAdvance('review', {
      accountEmail: accountEmail.value,
      termsAccepted: termsAccepted.value,
    }),
)
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
    title: __('Accept Terms'),
    description: __(
      'Confirm your facilities, accept the Terms, and submit your token package order.',
    ),
  },
  {
    title: __('Track progress'),
    description: __(
      'Track your progress in the portal through launch.',
    ),
  },
]
const progressSteps = computed(() =>
  STEPS.map((step) => {
    const status = stepStatus(step.key, stage.value)
    return {
      key: step.key,
      label: __(step.label),
      status,
      statusLabel:
        status === 'complete'
          ? __('complete')
          : status === 'current'
            ? __('current step')
            : __('upcoming'),
    }
  }),
)
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
function isSessionError(error) {
  return (
    error?.exc_type === 'PermissionError' ||
    /expired|session/i.test(error?.messages?.[0] || '')
  )
}
function stopResendTimer() {
  if (resendTimer) clearInterval(resendTimer)
  resendTimer = null
}
function applyDelivery(next) {
  delivery.value = next || {}
  resendIn.value = Number(next?.resend_after ?? 60)
  stopResendTimer()
  resendTimer = setInterval(() => {
    if (resendIn.value > 0) resendIn.value -= 1
    else stopResendTimer()
  }, 1000)
}
onBeforeUnmount(stopResendTimer)
async function startIdentity() {
  errorMessage.value = ''
  sessionExpired.value = false
  termsSnapshot.value = null
  termsAccepted.value = false
  busy.value = true
  try {
    const data = await request('start_identity', {
      identification_type: identityType.value,
      identification_number: identityNumber.value,
    })
    sessionToken.value = data.session_token
    identityPreview.value = data.identity || {}
    otp.value = ''
    otpError.value = ''
    hfrRetryPending.value = false
    hfrRetryExhausted.value = false
    applyDelivery(data.delivery)
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
  otpError.value = ''
  busy.value = true
  try {
    const data = await request('resend_otp', {
      session_token: sessionToken.value,
    })
    otp.value = ''
    applyDelivery(data.delivery)
  } catch (error) {
    sessionExpired.value = isSessionError(error)
    errorMessage.value =
      error?.messages?.[0] || __('We could not resend the code.')
  } finally {
    busy.value = false
  }
}
async function verifyOtp() {
  errorMessage.value = ''
  otpError.value = ''
  busy.value = true
  try {
    const data = await request('verify_otp', {
      session_token: sessionToken.value,
      otp: otp.value,
    })
    if (data.state === 'hfr_pending') {
      hfrRetryPending.value = true
      hfrRetryExhausted.value = !data.retryable
    } else {
      acceptFacilities(data)
    }
  } catch (error) {
    if (shouldClearOtpAfterVerificationError(error?.exc_type)) otp.value = ''
    // The server may have consumed the code and started HFR before a proxy or
    // connection dropped the response. Probe only the verified-session retry
    // endpoint; an unverified session receives the same generic denial.
    try {
      const recovered = await request('retry_hfr', {
        session_token: sessionToken.value,
      })
      if (recovered.state === 'hfr_pending') {
        hfrRetryPending.value = true
        hfrRetryExhausted.value = !recovered.retryable
      } else {
        acceptFacilities(recovered)
      }
      return
    } catch {
      otpError.value =
        error?.messages?.[0] || __('The code is incorrect or expired.')
    }
  } finally {
    busy.value = false
  }
}
function acceptFacilities(data) {
  identityPreview.value = data.identity || identityPreview.value
  facilities.value = data.facilities || []
  hfrRetryPending.value = false
  hfrRetryExhausted.value = false
  stage.value = 'facilities'
  stopResendTimer()
}
async function retryHfr() {
  errorMessage.value = ''
  busy.value = true
  try {
    const data = await request('retry_hfr', {
      session_token: sessionToken.value,
    })
    if (data.state === 'hfr_pending') {
      hfrRetryPending.value = true
      hfrRetryExhausted.value = !data.retryable
    } else {
      acceptFacilities(data)
    }
  } catch (error) {
    sessionExpired.value = isSessionError(error)
    errorMessage.value =
      error?.messages?.[0] || __('We could not retry the facility lookup.')
  } finally {
    busy.value = false
  }
}
function editIdentity() {
  stopResendTimer()
  sessionToken.value = ''
  otp.value = ''
  otpError.value = ''
  delivery.value = {}
  resendIn.value = 0
  sessionExpired.value = false
  hfrRetryPending.value = false
  hfrRetryExhausted.value = false
  termsSnapshot.value = null
  termsAccepted.value = false
  errorMessage.value = ''
  stage.value = 'identity'
}
function goBack() {
  const previous = previousStage(stage.value)
  if (previous) stage.value = previous
}
function continueFacilities() {
  if (selectedFacilities.value.length) {
    stage.value = 'pricing'
    loadCatalog()
  }
}
async function loadCatalog() {
  errorMessage.value = ''
  catalogBusy.value = true
  try {
    const previousPackage = packageCode.value
    catalog.value = await request('get_catalog', {
      partner_id: partnerId.value,
    })
    packageCode.value = catalog.value.packages?.some(
      (item) => item.item_code === previousPackage,
    )
      ? previousPackage
      : catalog.value.packages?.[0]?.item_code || ''
  } catch (error) {
    catalog.value = { network: null, packages: [] }
    errorMessage.value =
      error?.messages?.[0] || __('That Partner ID is not available.')
  } finally {
    catalogBusy.value = false
  }
}
async function loadSelfOnboardingTerms() {
  errorMessage.value = ''
  termsAccepted.value = false
  termsSnapshot.value = null
  termsBusy.value = true
  try {
    termsSnapshot.value = await request('get_self_onboarding_terms', {
      session_token: sessionToken.value,
    })
    return true
  } catch (error) {
    errorMessage.value =
      error?.messages?.[0] ||
      __('We could not load the current Terms and Conditions.')
    return false
  } finally {
    termsBusy.value = false
  }
}
async function continuePricing() {
  if (!catalog.value.network || !packageCode.value || termsBusy.value) return
  if (await loadSelfOnboardingTerms()) stage.value = 'review'
}
function conflictMessage(result) {
  if (result?.outcome === 'facility_level_ineligible') {
    const ineligible = new Set(result.ineligible_facility_ids || [])
    const eligibilityById = new Map(
      (result.facility_eligibility || []).map((status) => [
        status.facility_id,
        status,
      ]),
    )
    facilities.value = facilities.value.map((facility) =>
      eligibilityById.has(facility.facility_id) ||
      ineligible.has(facility.facility_id)
        ? {
            ...facility,
            ...(eligibilityById.get(facility.facility_id) || {
              onboarding_eligible: false,
              facility_eligibility_reason: 'level_not_allowed',
            }),
          }
        : facility,
    )
    selectedFacilities.value = selectedFacilities.value.filter(
      (facilityId) => !ineligible.has(facilityId),
    )
    stage.value = 'facilities'
    return __(
      'Facility level eligibility changed while you were onboarding. Review the facilities and continue with approved levels.',
    )
  }
  if (result?.outcome === 'existing_identity') {
    return __(
      'An onboarding request already exists for this identity. Sign in to your Customer Experience account or contact support for help.',
    )
  }
  if (result?.outcome === 'facility_review') {
    const allowed = new Set(result.allowed_facility_ids || [])
    const names = facilities.value
      .filter(
        (facility) =>
          selectedFacilities.value.includes(facility.facility_id) &&
          !allowed.has(facility.facility_id),
      )
      .map((facility) => facility.facility_name || facility.mfl_code)
    const selectedNames = names.length ? `: ${names.join(', ')}` : ''
    return `${__('One or more selected facilities already have an onboarding request for this Network')}${selectedNames}. ${__('Remove them from your selection and try again.')}`
  }
  return ''
}
async function submit() {
  if (!reviewReady.value) return
  errorMessage.value = ''
  registrationConflictDetected.value = false
  busy.value = true
  try {
    const conflict = await request('check_onboarding_conflicts', {
      session_token: sessionToken.value,
      partner_id: partnerId.value,
      selected_facility_ids: JSON.stringify(selectedFacilities.value),
    })
    const preflightMessage = conflictMessage(conflict)
    if (preflightMessage) {
      errorMessage.value = preflightMessage
      registrationConflictDetected.value = ['existing_identity', 'facility_review'].includes(
        conflict?.outcome,
      )
      return
    }
    if (conflict?.outcome !== 'new') {
      errorMessage.value = __(
        'We could not verify this onboarding selection. Please try again.',
      )
      return
    }
    const data = await request('submit_onboarding', {
      session_token: sessionToken.value,
      partner_id: partnerId.value,
      selected_facility_ids: JSON.stringify(selectedFacilities.value),
      package_item_code: packageCode.value,
      account_email: accountEmail.value,
      terms_accepted: termsAccepted.value ? 1 : 0,
      accepted_terms_hash: termsSnapshot.value.content_hash,
    })
    const submitConflict = conflictMessage(data)
    if (submitConflict) {
      errorMessage.value = submitConflict
      registrationConflictDetected.value = ['existing_identity', 'facility_review'].includes(
        data?.outcome,
      )
      return
    }
    if (data?.outcome && data.outcome !== 'new') {
      errorMessage.value = __(
        'We could not verify this onboarding selection. Please try again.',
      )
      return
    }
    submissions.value = data.enrollments || []
    stage.value = 'success'
  } catch (error) {
    sessionExpired.value = isSessionError(error)
    const message =
      error?.messages?.[0] ||
      __('We could not complete onboarding. Please try again.')
    if (/terms/i.test(message)) {
      const refreshed = await loadSelfOnboardingTerms()
      errorMessage.value = refreshed
        ? __(
            'The Terms have changed. Review and accept the updated Terms before submitting.',
          )
        : message
    } else {
      errorMessage.value = message
    }
  } finally {
    busy.value = false
  }
}
function reset() {
  stage.value = 'welcome'
  errorMessage.value = ''
  registrationConflictDetected.value = false
  sessionExpired.value = false
  hfrRetryPending.value = false
  hfrRetryExhausted.value = false
  sessionToken.value = ''
  otp.value = ''
  otpError.value = ''
  delivery.value = {}
  stopResendTimer()
  facilities.value = []
  selectedFacilities.value = []
  catalog.value = { network: null, packages: [] }
  packageCode.value = ''
  termsSnapshot.value = null
  termsAccepted.value = false
}
</script>
