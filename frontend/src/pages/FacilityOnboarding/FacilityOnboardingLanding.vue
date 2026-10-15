<template>
  <main class="min-h-screen bg-[#f6f7f8] text-ink-gray-9 relative isolate">
    <div class="pointer-events-none fixed inset-0 -z-10 overflow-hidden" aria-hidden="true">
      <div class="absolute -top-40 right-1/4 h-96 w-96 rounded-full bg-[radial-gradient(circle,rgba(188,24,35,0.06)_0%,transparent_65%)] blur-2xl"></div>
      <div class="absolute top-1/2 -left-24 h-96 w-96 rounded-full bg-[radial-gradient(circle,rgba(16,185,129,0.05)_0%,transparent_65%)] blur-2xl"></div>
    </div>
    <header class="sticky top-0 z-30 border-b border-outline-gray-2 bg-white/80 backdrop-blur-md">
      <div
        class="mx-auto flex max-w-6xl items-center justify-between px-5 py-3.5 sm:px-8"
      >
        <div class="flex items-center gap-3">
          <div
            class="flex size-9 items-center justify-center rounded-xl bg-[#bc1823] text-white font-semibold text-base shadow-sm"
          >
            T
          </div>
          <div>
            <p class="text-sm font-semibold tracking-tight text-ink-gray-9">
              Tiberbu <span class="font-normal text-ink-gray-5">Customer Experience</span>
            </p>
            <p class="text-[11px] font-medium text-ink-gray-5 flex items-center gap-1.5">
              <span class="inline-block size-1.5 rounded-full bg-emerald-500"></span>
              {{ __('Secure facility onboarding') }}
            </p>
          </div>
        </div>
        <div class="flex items-center gap-3 text-xs sm:text-sm">
          <a
            v-if="supportEmail"
            :href="`mailto:${supportEmail}`"
            class="inline-flex items-center gap-1.5 font-medium text-ink-gray-6 hover:text-ink-gray-9 transition"
          >
            <svg class="size-4 text-ink-gray-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 5.636l-3.536 3.536m0 5.656l3.536 3.536M9.172 9.172L5.636 5.636m3.536 9.192l-3.536 3.536M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-5 0a4 4 0 11-8 0 4 4 0 018 0z" />
            </svg>
            <span class="hidden sm:inline">{{ __('Need help?') }}</span>
          </a>
          <a
            href="/login?redirect-to=/cx-portal"
            class="inline-flex items-center gap-1.5 rounded-xl border border-outline-gray-2 bg-white/90 px-3.5 py-1.5 font-medium text-ink-gray-7 shadow-sm transition hover:bg-surface-gray-1 hover:text-ink-gray-9"
          >
            {{ __('Already have access? Sign in') }}
          </a>
        </div>
      </div>
    </header>
    <div class="mx-auto max-w-6xl px-5 py-8 sm:px-8 sm:py-12">
      <section
        v-if="stage === 'welcome'"
        class="grid gap-10 lg:grid-cols-[1.08fr_.92fr] lg:items-center"
      >
        <div>
          <span
            class="inline-flex items-center gap-1.5 rounded-full border border-[#f0d6d8] bg-[#fdf2f3] px-3 py-1 text-xs font-semibold uppercase tracking-wider text-[#bc1823]"
          >
            <span class="size-1.5 rounded-full bg-[#bc1823]"></span>
            {{ __('Start your facility journey') }}
          </span>
          <h1
            class="mt-4 max-w-2xl text-4xl font-semibold leading-tight tracking-tight text-ink-gray-9 sm:text-5xl lg:text-6xl"
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
          <div class="mt-8 flex flex-wrap items-center gap-4">
            <button
              class="inline-flex min-h-12 items-center gap-2 rounded-xl bg-[#bc1823] px-7 text-sm font-semibold text-white shadow-sm transition-all hover:bg-[#a3141d]"
              @click="stage = 'identity'"
            >
              <span>{{ __('Start secure onboarding') }}</span>
              <span class="text-lg">→</span>
            </button>
          </div>
          <p class="mt-4 text-xs font-medium text-ink-gray-5">
            {{ __('Usually 5–10 minutes · all displayed prices exclude VAT') }}
          </p>
        </div>
        <aside
          class="rounded-2xl border border-outline-gray-2 bg-white/90 p-6 shadow-sm backdrop-blur-md sm:p-8"
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
                class="flex size-8 shrink-0 items-center justify-center rounded-xl bg-[#fdf2f3] text-xs font-semibold text-[#bc1823] border border-[#f0d6d8]"
                >{{ index + 1 }}</span
              ><span
                ><strong class="block text-sm font-semibold text-ink-gray-9">{{ item.title }}</strong
                ><span class="mt-1 block text-sm leading-6 text-ink-gray-6">{{
                  item.description
                }}</span></span
              >
            </li>
          </ol>
          <div
            class="mt-7 flex items-start gap-3 rounded-xl bg-surface-gray-1 border border-outline-gray-2 p-4 text-xs leading-5 text-ink-gray-6"
          >
            <svg class="size-5 shrink-0 text-emerald-600 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
            <span>
              {{
                __(
                  'Your identity and facility details are checked through the registry. We do not reveal whether an ID exists until the verification step succeeds.',
                )
              }}
            </span>
          </div>
        </aside>
      </section>
      <section
        v-if="stage === 'welcome'"
        class="mt-10 rounded-2xl border border-outline-gray-2 bg-white/90 p-6 shadow-sm sm:p-8 backdrop-blur-md"
        aria-labelledby="hmis-about-title"
      >
        <span
          class="inline-flex items-center gap-1.5 rounded-full border border-outline-gray-2 bg-surface-gray-2 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider text-ink-gray-7"
        >
          {{ __('About Tiberbu HMIS') }}
        </span>
        <h2 id="hmis-about-title" class="mt-3 text-xl font-semibold text-ink-gray-9">
          {{
            __('One connected path from verification to Customer Experience')
          }}
        </h2>
        <p class="mt-2.5 max-w-3xl text-sm leading-6 text-ink-gray-6">
          {{
            __(
              'Tiberbu HMIS connects identity checks, facility selection, token package orders and Customer Experience access. This wizard is for facility owners and administrators.',
            )
          }}
        </p>
        <a
          href="/login?redirect-to=/crm"
          class="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-[#bc1823] hover:text-[#a3141d] underline underline-offset-4"
        >
          <span>{{ __('Staff access') }}</span>
          <span>→</span>
        </a>
      </section>
      <section v-else class="mx-auto max-w-3xl">
        <div class="mb-6 flex flex-wrap items-center justify-between gap-4">
          <div>
            <span
              class="inline-flex items-center gap-1.5 rounded-full border border-[#f0d6d8] bg-[#fdf2f3] px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider text-[#bc1823]"
            >
              <span class="size-1.5 rounded-full bg-[#bc1823]"></span>
              {{ __('Facility onboarding') }}
            </span>
            <h1 class="mt-2 text-2xl font-semibold tracking-tight text-ink-gray-9 sm:text-3xl">
              {{ stageTitle }}
            </h1>
          </div>
          <button
            v-if="stage !== 'success'"
            type="button"
            class="inline-flex items-center gap-1.5 rounded-xl border border-outline-gray-2 bg-white px-3.5 py-1.5 text-xs font-semibold text-ink-gray-6 shadow-sm transition hover:bg-surface-gray-1 hover:text-ink-gray-9"
            @click="reset"
          >
            <svg class="size-3.5 text-ink-gray-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            {{ __('Start over') }}
          </button>
        </div>
        <ol
          v-if="stage !== 'success'"
          class="mb-8 grid grid-cols-4 gap-2 sm:gap-4 rounded-2xl border border-outline-gray-2 bg-white/85 p-3 sm:p-4 shadow-sm backdrop-blur-md"
          :aria-label="__('Onboarding steps')"
        >
          <li
            v-for="(item, index) in progressSteps"
            :key="item.key"
            class="relative flex flex-col items-center sm:items-start transition-all"
            :aria-current="item.status === 'current' ? 'step' : undefined"
          >
            <div class="flex items-center w-full mb-2">
              <span
                class="flex size-7 sm:size-8 items-center justify-center rounded-xl text-xs font-bold transition-all duration-200 shrink-0"
                :class="
                  item.status === 'complete'
                    ? 'bg-emerald-600 text-white shadow-sm ring-4 ring-emerald-100'
                    : item.status === 'current'
                      ? 'bg-[#bc1823] text-white shadow-sm ring-4 ring-[#bc1823]/20'
                      : 'bg-surface-gray-2 text-ink-gray-7 border border-outline-gray-3'
                "
              >
                <template v-if="item.status === 'complete'">✓</template>
                <template v-else>{{ index + 1 }}</template>
              </span>
              <div
                v-if="index < progressSteps.length - 1"
                class="hidden sm:block flex-1 h-0.5 mx-2 rounded-full transition-colors duration-200"
                :class="item.status === 'complete' ? 'bg-emerald-600' : 'bg-outline-gray-3'"
              />
            </div>
            <div class="text-center sm:text-left min-w-0 w-full">
              <span
                class="block truncate text-xs sm:text-sm font-semibold tracking-tight transition-colors"
                :class="
                  item.status === 'upcoming'
                    ? 'text-ink-gray-6 font-normal'
                    : item.status === 'current'
                      ? 'text-[#bc1823] font-bold'
                      : 'text-ink-gray-9 font-semibold'
                "
              >
                {{ item.label }}
                <span class="sr-only"> — {{ item.statusLabel }}</span>
              </span>
              <span class="hidden sm:block truncate text-[11px] font-normal transition-colors"
                :class="item.status === 'current' ? 'text-[#bc1823]/80 font-medium' : 'text-ink-gray-6'"
              >
                {{ stepSubtitles[item.key] }}
              </span>
            </div>
          </li>
        </ol>
        <div
          v-if="errorMessage"
          class="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-rose-200 bg-rose-50/90 p-4 text-sm text-rose-900 shadow-sm backdrop-blur"
          role="alert"
        >
          <div class="flex items-center gap-2.5">
            <span class="flex size-7 shrink-0 items-center justify-center rounded-lg bg-rose-200/80 text-rose-700">
              <svg class="size-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </span>
            <span>{{ errorMessage }}</span>
          </div>
          <div class="flex items-center gap-3">
            <a
              v-if="registrationConflictDetected"
              href="/login?redirect-to=/cx-portal"
              data-testid="duplicate-signin"
              class="font-semibold text-rose-700 underline underline-offset-4 hover:text-rose-900"
              >{{ __('Sign in to Customer Experience') }}</a
            ><a
              v-if="registrationConflictDetected && supportEmail"
              :href="`mailto:${supportEmail}`"
              data-testid="duplicate-support"
              class="font-semibold text-rose-700 underline underline-offset-4 hover:text-rose-900"
              >{{ __('Contact support') }}</a
            ><button
              v-if="sessionExpired"
              type="button"
              class="font-semibold text-rose-700 underline underline-offset-4 hover:text-rose-900"
              @click="reset"
            >
              {{ __('Start again') }}
            </button>
          </div>
        </div>
        <form
          v-if="stage === 'identity'"
          class="rounded-2xl border border-outline-gray-2 bg-white/90 p-6 shadow-sm backdrop-blur-md sm:p-9"
          @submit.prevent="startIdentity"
        >
          <div class="flex items-start gap-4">
            <div class="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-[#fdf2f3] border border-[#f0d6d8] text-[#bc1823] shadow-sm">
              <svg class="size-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <div>
              <h2 class="text-lg font-semibold text-ink-gray-9">
                {{ __('Verify Facility Ownership') }}
              </h2>
              <p class="mt-1 text-sm leading-6 text-ink-gray-6">
                {{
                  __(
                    'Enter the ID used to register as the facility owner. We will check the registered contact first and look up facility details after you verify the code.',
                  )
                }}
              </p>
            </div>
          </div>

          <div class="mt-8 space-y-6">
            <div>
              <label class="block text-xs font-semibold uppercase tracking-wider text-ink-gray-7">
                {{ __('Identification type') }}
              </label>
              <div class="relative mt-2">
                <select
                  v-model="identityType"
                  class="block w-full rounded-xl border border-outline-gray-2 bg-white px-4 py-3 text-sm font-medium text-ink-gray-9 shadow-sm transition focus:border-[#bc1823] focus:outline-none focus:ring-4 focus:ring-[#bc1823]/10"
                >
                  <option value="national_id">{{ __('National ID') }}</option>
                  <option value="passport">{{ __('Passport') }}</option>
                  <option value="foreigner_id">{{ __('Foreigner ID') }}</option>
                  <option value="alien_id">{{ __('Alien ID') }}</option>
                </select>
              </div>
            </div>

            <div>
              <label class="block text-xs font-semibold uppercase tracking-wider text-ink-gray-8">
                {{ __('Identification number') }}
              </label>
              <div class="relative mt-2">
                <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-ink-gray-5">
                  <svg class="size-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V8a2 2 0 00-2-2h-5m-4 0V5a2 2 0 114 0v1m-4 0a2 2 0 104 0m-5 8a2 2 0 100-4 2 2 0 000 4zm0 0c1.306 0 2.417.835 2.83 2M9 14a3.001 3.001 0 00-2.83 2M15 11h3m-3 4h2" />
                  </svg>
                </div>
                <input
                  v-model.trim="identityNumber"
                  required
                  autocomplete="off"
                  class="block w-full rounded-xl border border-outline-gray-2 bg-white pl-11 pr-4 py-3 text-sm font-medium text-ink-gray-9 placeholder:text-ink-gray-5 shadow-sm transition focus:border-[#bc1823] focus:outline-none focus:ring-4 focus:ring-[#bc1823]/10"
                  :placeholder="__('Enter your ID number')"
                />
              </div>
            </div>
          </div>

          <button
            :disabled="busy"
            class="mt-8 flex min-h-12 w-full items-center justify-center gap-2 rounded-xl px-6 text-sm font-semibold transition-all shadow-sm"
            :class="
              busy
                ? 'bg-surface-gray-3 text-ink-gray-5 border border-outline-gray-3 cursor-not-allowed shadow-none'
                : 'bg-[#bc1823] text-white hover:bg-[#a3141d]'
            "
          >
            <span>{{ busy ? __('Checking…') : __('Find my facilities') }}</span>
            <span v-if="!busy" class="text-base">→</span>
          </button>
          <div class="mt-5 flex items-center justify-center gap-2 text-center text-xs text-ink-gray-7 font-medium">
            <svg class="size-4 text-emerald-700 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
            <span>
              {{
                __(
                  'A one-time verification code will be sent to the contact registered against your ID.',
                )
              }}
            </span>
          </div>
        </form>
        <form
          v-else-if="stage === 'otp'"
          class="rounded-2xl border border-outline-gray-2 bg-white/90 p-6 shadow-sm backdrop-blur-md sm:p-9"
          @submit.prevent="verifyOtp"
        >
          <div
            v-if="hfrRetryPending"
            class="rounded-xl border border-amber-200 bg-amber-50/90 p-5 text-sm leading-6 text-amber-900 shadow-sm"
            role="status"
          >
            <div class="flex items-start gap-3">
              <svg class="size-5 shrink-0 text-amber-600 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <div>
                <p class="font-medium">
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
                  class="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-amber-100 px-3 py-1.5 text-xs font-semibold text-amber-900 hover:bg-amber-200 disabled:opacity-50"
                  @click="retryHfr"
                >
                  <svg class="size-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  <span>{{
                    busy ? __('Checking facilities…') : __('Retry facility lookup')
                  }}</span>
                </button>
              </div>
            </div>
          </div>
          <template v-else>
            <div
              v-if="deliveryStatus === 'unavailable'"
              class="rounded-xl border border-amber-200 bg-amber-50/90 p-4 text-sm leading-6 text-amber-900"
              role="status"
            >
              {{
                __(
                  'We could not deliver a code just now. Retry delivery to this verified contact session.',
                )
              }}
            </div>
            <div v-else class="text-center" role="status">
              <div class="mx-auto flex size-12 items-center justify-center rounded-2xl bg-[#fdf2f3] border border-[#f0d6d8] text-[#bc1823] shadow-sm mb-4">
                <svg class="size-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
                </svg>
              </div>
              <h2 class="text-lg font-semibold text-ink-gray-9">
                {{ __('Enter Verification Code') }}
              </h2>
              <p class="mx-auto mt-2 max-w-md text-sm leading-6 text-ink-gray-6">
                {{
                  delivery.masked_destination
                    ? __('A 6-digit code was sent by {0} to {1}.', [
                        deliveryChannelLabel,
                        delivery.masked_destination,
                      ])
                    : __(
                        'If your details match our records, a 6-digit code was sent to the registered contact.',
                      )
                }}
              </p>
              <div class="mt-2 inline-flex items-center gap-1.5 rounded-full bg-surface-gray-2 border border-outline-gray-3 px-3 py-1 text-xs font-semibold text-ink-gray-7">
                <svg class="size-3.5 text-ink-gray-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>{{ __('The code expires in {0} minutes.', [expiryMinutes]) }}</span>
              </div>
            </div>
            <div class="mt-8">
              <OtpCodeInput
                v-model="otp"
                :disabled="busy"
                :error="otpError"
                :label="__('Verification code')"
              />
            </div>
            <button
              :disabled="busy || otp.length !== 6"
              class="mt-8 flex min-h-12 w-full items-center justify-center gap-2 rounded-xl px-6 text-sm font-semibold transition-all shadow-sm"
              :class="
                busy || otp.length !== 6
                  ? 'bg-surface-gray-3 text-ink-gray-5 border border-outline-gray-3 cursor-not-allowed shadow-none'
                  : 'bg-[#bc1823] text-white hover:bg-[#a3141d]'
              "
            >
              <span>{{ busy ? __('Verifying…') : __('Verify and continue') }}</span>
              <span v-if="!busy" class="text-base">→</span>
            </button>
            <div class="mt-4 flex flex-col gap-2 sm:flex-row sm:justify-between">
              <button
                type="button"
                :disabled="!canResendOtp(delivery, resendIn, busy)"
                class="min-h-11 rounded-xl px-4 text-xs font-semibold text-[#bc1823] hover:text-[#a3141d] hover:bg-[#fdf2f3] disabled:text-ink-gray-5 disabled:hover:bg-transparent transition"
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
                class="min-h-11 rounded-xl px-4 text-xs font-semibold text-ink-gray-6 hover:text-ink-gray-9 hover:bg-surface-gray-1 disabled:text-ink-gray-5 disabled:hover:bg-transparent transition"
                @click="editIdentity"
              >
                {{ __('Edit ID details') }}
              </button>
            </div>
          </template>
        </form>
        <form
          v-else-if="stage === 'facilities'"
          class="space-y-6"
          @submit.prevent="continueFacilities"
        >
          <div
            class="rounded-2xl border border-outline-gray-2 bg-white/90 p-6 shadow-sm backdrop-blur-md sm:p-9"
          >
            <section
              v-if="
                identityPreview.full_name ||
                identityPreview.email ||
                identityPreview.phone
              "
              class="mb-7 rounded-2xl border-2 border-[#f0d6d8] bg-[#fdf2f3] p-5 shadow-sm"
              :aria-label="__('Verified identity')"
            >
              <div class="flex items-center gap-3.5">
                <div class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-emerald-600 text-white font-bold text-base shadow-sm ring-4 ring-emerald-100">
                  ✓
                </div>
                <div>
                  <div class="flex items-center gap-2">
                    <h2 class="text-sm font-bold text-ink-gray-9">
                      {{ __('Verified identity') }}
                    </h2>
                    <span class="rounded-full bg-white border border-[#bc1823]/30 px-2.5 py-0.5 text-[10px] font-bold text-[#bc1823] uppercase tracking-wide">
                      {{ __('Registry Verified') }}
                    </span>
                  </div>
                  <p
                    v-if="identityPreview.full_name"
                    class="mt-0.5 text-base sm:text-lg font-bold text-ink-gray-9"
                  >
                    {{ identityPreview.full_name }}
                  </p>
                </div>
              </div>
              <div class="mt-4 grid gap-2 border-t border-[#f0d6d8] pt-3 text-xs sm:grid-cols-2">
                <p
                  v-if="identityPreview.email"
                  class="flex items-center gap-2 font-semibold text-ink-gray-8"
                >
                  <span class="text-ink-gray-6 font-bold">✉</span>
                  <span>{{ __('Email: {0}', [identityPreview.email]) }}</span>
                </p>
                <p
                  v-if="identityPreview.phone"
                  class="flex items-center gap-2 font-semibold text-ink-gray-8"
                >
                  <span class="text-ink-gray-6 font-bold">✆</span>
                  <span>{{ __('Phone: {0}', [identityPreview.phone]) }}</span>
                </p>
              </div>
            </section>

            <div>
              <h3 class="text-base font-semibold text-ink-gray-9">
                {{ __('Select facilities to onboard') }}
              </h3>
              <p class="mt-1 text-sm leading-6 text-ink-gray-7">
                {{
                  __(
                    'Select all eligible facilities you want to add under the same Opt-In Network.',
                  )
                }}
              </p>
            </div>

            <p
              v-if="!facilities.length"
              class="mt-6 rounded-2xl border border-outline-gray-2 bg-surface-gray-1 p-5 text-sm leading-6 text-ink-gray-7"
              role="status"
            >
              {{
                __(
                  'No eligible facilities were returned for this verified identity. Contact support if you think this is an error.',
                )
              }}
            </p>
            <div class="mt-6 space-y-3.5">
              <label
                v-for="facility in facilities"
                :key="facility.facility_id"
                class="flex gap-4 rounded-2xl border p-5 transition-all"
                :class="
                  facility.onboarding_eligible !== true || facility.onboarding_blocked
                    ? 'cursor-not-allowed border-outline-gray-2 bg-surface-gray-1'
                    : selectedFacilities.includes(facility.facility_id)
                      ? 'cursor-pointer border-2 border-[#bc1823] bg-[#fdf2f3] ring-2 ring-[#bc1823]/20 shadow-sm'
                      : 'cursor-pointer border border-outline-gray-2 bg-white hover:border-[#f0d6d8] hover:shadow-sm'
                "
              >
                <input
                  v-model="selectedFacilities"
                  type="checkbox"
                  :value="facility.facility_id"
                  :disabled="facility.onboarding_eligible !== true || facility.onboarding_blocked"
                  class="mt-1 size-5 rounded border-outline-gray-2 text-[#bc1823] accent-[#bc1823] focus:ring-[#bc1823]/20 disabled:cursor-not-allowed disabled:opacity-40"
                />
                <div class="min-w-0 flex-1">
                  <div class="flex flex-wrap items-center justify-between gap-2">
                    <strong class="text-base font-bold text-ink-gray-9">
                      {{ facility.facility_name || facility.mfl_code }}
                    </strong>
                    <span
                      v-if="facility.facility_level || facility.classification"
                      class="inline-flex items-center rounded-full bg-surface-gray-2 border border-outline-gray-3 px-2.5 py-0.5 text-xs font-semibold text-ink-gray-8"
                    >
                      {{ facility.facility_level || facility.classification }}
                    </span>
                  </div>
                  <div class="mt-1.5 flex flex-wrap items-center gap-2 text-xs">
                    <span class="font-semibold text-ink-gray-8">{{ facility.facility_type || __('Facility') }}</span>
                    <span class="text-ink-gray-4">·</span>
                    <span class="text-ink-gray-7">{{ facility.classification || __('Classification pending') }}</span>
                    <span class="text-ink-gray-4">·</span>
                    <span class="rounded bg-white px-1.5 py-0.5 font-mono text-[11px] font-bold text-ink-gray-9 border border-outline-gray-3">
                      {{ facility.mfl_code }}
                    </span>
                  </div>
                  <span
                    v-if="facility.onboarding_blocked"
                    class="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-rose-50 border border-rose-200 px-3 py-1.5 text-xs font-bold text-rose-800"
                    data-testid="facility-already-onboarded"
                  >
                    <svg class="size-4 shrink-0 text-rose-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    {{ __('Already onboarded. This facility cannot be selected to proceed.') }}
                  </span>
                  <span
                    v-else-if="facility.onboarding_eligible !== true"
                    class="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-amber-50 border border-amber-200 px-3 py-1.5 text-xs font-bold text-amber-900"
                  >
                    <svg class="size-4 shrink-0 text-amber-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    {{
                      facility.facility_eligibility_reason === 'missing_level'
                        ? __(
                            'Unavailable for token self-onboarding because HFR did not return a Facility Level.',
                          )
                        : __(
                            'Unavailable for token self-onboarding because this Facility Level is not approved.',
                          )
                    }}
                  </span>
                </div>
              </label>
            </div>
          </div>
          <button
            :disabled="!selectedFacilities.length"
            class="flex min-h-12 w-full items-center justify-center gap-2 rounded-xl px-6 text-sm font-semibold transition-all shadow-sm"
            :class="
              !selectedFacilities.length
                ? 'bg-surface-gray-3 text-ink-gray-5 border border-outline-gray-3 cursor-not-allowed shadow-none'
                : 'bg-[#bc1823] text-white hover:bg-[#a3141d]'
            "
          >
            <span>{{ __('Continue to pricing') }}</span>
            <span class="text-base">→</span>
          </button>
        </form>
        <form
          v-else-if="stage === 'pricing'"
          class="space-y-6"
          @submit.prevent="continuePricing"
        >
          <div
            class="rounded-2xl border border-outline-gray-2 bg-white/90 p-6 shadow-sm backdrop-blur-md sm:p-9"
          >
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div>
                <span
                  v-if="catalog.network?.display_name"
                  class="inline-flex items-center gap-1.5 rounded-full border border-[#f0d6d8] bg-[#fdf2f3] px-3 py-1 text-xs font-semibold text-[#bc1823]"
                >
                  <span class="size-1.5 rounded-full bg-emerald-500"></span>
                  {{ catalog.network.display_name }}
                </span>
                <h2 class="mt-2 text-2xl font-semibold tracking-tight text-ink-gray-9">
                  {{ __('Choose a package for each facility') }}
                </h2>
              </div>
              <span class="text-xs font-medium text-ink-gray-5">
                {{ __('All displayed prices exclude VAT') }}
              </span>
            </div>
            <p
              v-if="catalog.network?.display_name"
              class="mt-2 text-sm leading-6 text-ink-gray-6"
            >
              {{
                __(
                  'Choose each facility’s package separately. Consider its size and expected token use.',
                )
              }}
            </p>
            <p v-else class="mt-2 text-sm leading-6 text-ink-gray-6">
              {{
                __(
                  'The token catalogue is available before you select the referring partner Network.',
                )
              }}
            </p>
            <p
              v-if="catalogBusy"
              class="mt-4 inline-flex items-center gap-2 rounded-xl bg-surface-gray-2 px-3.5 py-2 text-xs font-medium text-ink-gray-6"
              role="status"
              aria-live="polite"
              data-testid="catalog-loading"
            >
              <svg class="size-4 animate-spin text-[#bc1823]" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              <span>{{ __('Loading token packages and current pricing…') }}</span>
            </p>

            <section
              class="mt-6 rounded-xl border border-outline-gray-2 bg-surface-gray-1/70 p-5 shadow-sm"
            >
              <div class="flex items-center gap-2.5">
                <div class="flex size-7 items-center justify-center rounded-lg bg-[#fdf2f3] text-[#bc1823] font-semibold text-xs border border-[#f0d6d8]">
                  #
                </div>
                <h3 class="text-sm font-semibold text-ink-gray-9">
                  {{ __('Were you referred by a partner?') }}
                </h3>
              </div>
              <p class="mt-1 text-xs leading-5 text-ink-gray-6">
                {{
                  __(
                    'Enter the 6-digit Network ID your referring partner shared with you. Leave it blank to use Tiberbu’s configured default Network when one is available.',
                  )
                }}
              </p>
              <label class="mt-4 block text-xs font-semibold uppercase tracking-wider text-ink-gray-7">
                {{ __('Partner Network ID') }}
                <span class="ml-1 text-[11px] font-normal lowercase text-ink-gray-5">({{ __('optional') }})</span>
                <input
                  :value="partnerId"
                  inputmode="numeric"
                  autocomplete="off"
                  maxlength="6"
                  pattern="[0-9]{6}"
                  :aria-invalid="Boolean(partnerId && partnerId.length !== 6)"
                  :title="__('Enter all six digits or leave this field blank.')"
                  aria-describedby="partner-network-help"
                  class="mt-2 block w-full rounded-xl border border-outline-gray-2 bg-white px-4 py-2.5 font-mono text-sm shadow-sm transition focus:border-[#bc1823] focus:outline-none focus:ring-4 focus:ring-[#bc1823]/10"
                  placeholder="123456"
                  @input="onPartnerIdInput"
                />
              </label>
              <span
                id="partner-network-help"
                class="mt-2 block text-xs text-ink-gray-5"
              >
                {{
                  __(
                    'This existing Network will be linked to every facility you select. Your verified registry contact will be added as its Network Contact.',
                  )
                }}
              </span>
              <span
                v-if="partnerId && partnerId.length !== 6"
                class="mt-2 inline-flex items-center gap-1.5 text-xs font-semibold text-amber-700"
                role="status"
              >
                <svg class="size-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <span>{{
                  __(
                    'Enter all six digits, or clear the field to use the configured default Network if available.',
                  )
                }}</span>
              </span>
            </section>

            <div
              v-if="catalogBusy"
              class="mt-8 grid gap-4 sm:grid-cols-2"
              aria-hidden="true"
            >
              <div
                v-for="placeholder in 2"
                :key="placeholder"
                class="animate-pulse rounded-2xl border border-outline-gray-2 bg-surface-gray-1 p-6"
              >
                <div class="h-5 w-2/3 rounded-lg bg-surface-gray-2"></div>
                <div class="mt-4 h-6 w-1/3 rounded-lg bg-surface-gray-2"></div>
                <div class="mt-4 h-4 w-full rounded bg-surface-gray-2"></div>
              </div>
            </div>
            <div
              v-else-if="catalogError"
              class="mt-8 rounded-2xl border border-rose-200 bg-rose-50/90 p-5 text-sm shadow-sm"
              role="alert"
              data-testid="catalog-error"
            >
              <p class="font-medium text-rose-900">{{ catalogError }}</p>
              <button
                type="button"
                class="mt-3 inline-flex items-center gap-1.5 font-bold text-rose-700 underline underline-offset-4 hover:text-rose-900"
                @click="loadCatalog(true)"
              >
                {{ __('Try loading packages again') }} →
              </button>
            </div>
            <div
              v-else-if="partnerId && partnerId.length !== 6"
              class="mt-8 rounded-2xl border border-outline-gray-2 bg-surface-gray-1 p-5 text-sm text-ink-gray-6"
              role="status"
              data-testid="catalog-partner-incomplete"
            >
              {{ __('Enter all six digits to load this Network’s packages, or clear the field to use the configured default.') }}
            </div>
            <div
              v-else-if="!catalog.packages?.length"
              class="mt-8 rounded-2xl border border-outline-gray-2 bg-surface-gray-1 p-6 text-center text-sm text-ink-gray-6"
              role="status"
              data-testid="catalog-empty"
            >
              <p class="font-medium">{{ __('No token packages are available right now.') }}</p>
              <button
                type="button"
                class="mt-3 inline-flex items-center gap-1.5 font-bold text-[#bc1823] underline underline-offset-4 hover:text-[#a3141d]"
                @click="loadCatalog(true)"
              >
                {{ __('Try loading packages again') }} →
              </button>
            </div>
            <div v-else class="mt-8 space-y-8">
              <section
                v-for="facility in chosenFacilities"
                :key="facility.facility_id"
                class="rounded-2xl border border-outline-gray-2 bg-white/90 backdrop-blur-md p-6 sm:p-8 shadow-sm text-ink-gray-9"
                :data-testid="`facility-package-${facility.facility_id}`"
              >
                <div class="text-center max-w-2xl mx-auto mb-8 sm:mb-10">
                  <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#fdf2f3] border border-[#f0d6d8] text-xs text-[#bc1823] font-semibold mb-3">
                    <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
                    <span>{{ facility.facility_name || facility.mfl_code }} · {{ facility.classification || __('Facility') }}</span>
                  </div>
                  <h3 class="text-2xl sm:text-3xl font-semibold tracking-tight text-ink-gray-9">
                    {{ __('Pricing & Plans') }}
                  </h3>
                  <p class="mt-2 text-sm text-ink-gray-6">
                    {{ __('Simple, transparent pricing for individuals and teams.') }}
                  </p>
                </div>

                <div class="grid gap-5 sm:grid-cols-2 lg:grid-cols-4 items-stretch">
                  <article
                    v-for="item in catalog.packages"
                    :key="`${facility.facility_id}-${item.item_code}`"
                    class="relative rounded-2xl border p-6 flex flex-col justify-between transition-all duration-200 cursor-pointer shadow-sm"
                    :class="packageSelections[facility.facility_id] === item.item_code
                      ? 'border-2 border-[#bc1823] bg-[#fdf2f3]/30 ring-4 ring-[#bc1823]/10 shadow-md'
                      : 'border-outline-gray-2 bg-white/90 hover:border-[#f0d6d8] hover:shadow-md'"
                    @click="packageSelections[facility.facility_id] = item.item_code"
                  >
                    <div>
                      <div class="flex items-center justify-between gap-2">
                        <h4 class="text-lg font-semibold text-ink-gray-9 tracking-tight">
                          {{ item.display_name || item.item_code }}
                        </h4>
                        <span
                          v-if="packageMetadata(item).badge"
                          class="px-2 py-0.5 rounded text-[10px] font-semibold tracking-wider uppercase"
                          :class="Number(item.price_ex_vat ?? item.price ?? 0) === 0
                            ? 'bg-surface-gray-2 text-ink-gray-7 border border-outline-gray-2'
                            : 'bg-[#fdf2f3] text-[#bc1823] border border-[#f0d6d8]'"
                        >
                          {{ packageMetadata(item).badge }}
                        </span>
                      </div>

                      <div class="mt-3 flex items-baseline gap-1.5 flex-wrap">
                        <span
                          class="text-3xl font-semibold tracking-tight text-ink-gray-9"
                        >
                          {{ Number(item.price_ex_vat ?? item.price ?? 0) === 0 ? '$0' : money(item.price_ex_vat ?? item.price, item.currency) }}
                        </span>
                        <span class="text-xs text-ink-gray-6 font-medium">
                          {{ Number(item.price_ex_vat ?? item.price ?? 0) === 0 ? __('Free') : __('/ month (excl. VAT)') }}
                        </span>
                      </div>
                      <p v-if="item.gross_total" class="mt-1 text-[11px] text-ink-gray-7 font-medium">
                        {{ item.vat_label || __('VAT') }} {{ money(item.vat_amount, item.currency) }} · {{ __('Total') }} {{ money(item.gross_total, item.currency) }}
                      </p>

                      <p class="mt-2 text-xs text-ink-gray-7 leading-snug min-h-[1.75rem]">
                        {{ packageMetadata(item).audience }}
                      </p>

                      <div class="mt-4 flex items-center gap-2 rounded-lg bg-[#fdf2f3] px-3 py-2 text-xs font-semibold text-[#bc1823] border border-[#f0d6d8]">
                        <span class="text-amber-600">🪙</span>
                        <span><strong class="text-ink-gray-9">{{ item.token_quantity }}</strong> {{ __('Tokens included') }}</span>
                      </div>

                      <p class="mt-3 text-xs leading-relaxed text-ink-gray-7">
                        {{ item.coverage_summary || item.description }}
                      </p>

                      <div class="mt-6 pt-5 border-t border-outline-gray-2">
                        <p class="text-[10px] font-bold uppercase tracking-wider text-ink-gray-7 mb-3">
                          {{ Number(item.price_ex_vat ?? item.price ?? 0) === 0
                            ? __('FEATURES')
                            : (item.item_code?.includes('CORE') || item.display_name === 'Pro'
                              ? __('FREE FEATURES +')
                              : __('PRO FEATURES +'))
                          }}
                        </p>
                        <ul class="space-y-2.5 text-xs text-ink-gray-8">
                          <li
                            v-for="feature in packageMetadata(item).features"
                            :key="feature"
                            class="flex items-start gap-2.5"
                          >
                            <svg class="w-4 h-4 text-emerald-700 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/>
                            </svg>
                            <span class="font-medium">{{ feature }}</span>
                          </li>
                        </ul>
                      </div>
                    </div>

                    <div class="mt-8">
                      <button
                        type="button"
                        class="w-full py-2.5 px-4 rounded-xl text-xs font-semibold transition-all duration-150"
                        :class="packageSelections[facility.facility_id] === item.item_code
                          ? 'bg-[#bc1823] text-white shadow-sm hover:bg-[#a3141d]'
                          : 'border border-outline-gray-3 text-ink-gray-9 bg-white hover:bg-[#fdf2f3] hover:text-[#bc1823] hover:border-[#f0d6d8]'"
                        @click.stop="packageSelections[facility.facility_id] = item.item_code"
                      >
                        {{ packageSelections[facility.facility_id] === item.item_code ? __('✓ Selected') : __('Choose plan') }}
                      </button>
                      <input
                        v-model="packageSelections[facility.facility_id]"
                        type="radio"
                        :name="`package-${facility.facility_id}`"
                        :value="item.item_code"
                        class="sr-only"
                      />
                    </div>
                  </article>
                </div>
              </section>
            </div>
          </div>
          <button
            :disabled="catalogBusy || catalogError || !catalogCurrent || !allPackagesSelected || termsBusy"
            class="flex min-h-12 w-full items-center justify-center gap-2 rounded-xl px-6 text-sm font-semibold transition-all shadow-sm"
            :class="
              catalogBusy || catalogError || !catalogCurrent || !allPackagesSelected || termsBusy
                ? 'bg-surface-gray-3 text-ink-gray-5 border border-outline-gray-3 cursor-not-allowed shadow-none'
                : 'bg-[#bc1823] text-white hover:bg-[#a3141d]'
            "
          >
            <span>{{
              catalogBusy
                ? __('Loading token packages…')
                : termsBusy
                  ? __('Loading Terms…')
                  : __('Continue to submission review')
            }}</span>
            <span class="text-base">→</span>
          </button>
          <button
            type="button"
            class="min-h-11 w-full text-sm font-semibold text-ink-gray-6 hover:text-ink-gray-9 transition"
            @click="goBack"
          >
            {{ __('Back to facilities') }}
          </button>
        </form>
        <form
          v-else-if="stage === 'review'"
          class="space-y-6"
          @submit.prevent="submit"
        >
          <div
            class="rounded-2xl border border-outline-gray-2 bg-white/90 p-6 shadow-sm backdrop-blur-md sm:p-9"
          >
            <div class="flex items-center gap-3">
              <div class="flex size-10 items-center justify-center rounded-xl bg-surface-gray-2 text-ink-gray-7 font-semibold text-sm">
                📋
              </div>
              <div>
                <h2 class="text-xl font-semibold text-ink-gray-9">
                  {{ __('Review and confirm') }}
                </h2>
                <p class="mt-0.5 text-xs text-ink-gray-5">
                  {{
                    __(
                      'Confirm the facilities, account contact, Network and package before submitting.',
                    )
                  }}
                </p>
              </div>
            </div>

            <dl class="mt-7 divide-y divide-outline-gray-2 rounded-xl border border-outline-gray-2 bg-surface-gray-1/50 text-sm">
              <div class="flex items-center justify-between gap-4 p-4">
                <dt class="text-ink-gray-6 font-medium">
                  {{ __('Network') }}
                  <button
                    type="button"
                    class="ml-2 text-xs font-semibold text-[#bc1823] underline underline-offset-4 hover:text-[#a3141d]"
                    @click="stage = 'pricing'"
                  >
                    {{ __('Edit') }}
                  </button>
                </dt>
                <dd class="text-right font-semibold text-ink-gray-9" data-testid="review-network">
                  {{ catalog.network?.display_name || __('No Network resolved') }}
                </dd>
              </div>
              <div class="flex items-start justify-between gap-4 p-4">
                <dt class="text-ink-gray-6 font-medium">
                  {{ __('Facilities') }}
                  <button
                    type="button"
                    class="ml-2 text-xs font-semibold text-[#bc1823] underline underline-offset-4 hover:text-[#a3141d]"
                    @click="stage = 'facilities'"
                  >
                    {{ __('Edit') }}
                  </button>
                </dt>
                <dd class="text-right font-semibold text-ink-gray-9">
                  <span
                    v-for="facility in chosenFacilities"
                    :key="facility.facility_id"
                    class="block"
                    >{{ facility.facility_name || facility.mfl_code }}</span
                  >
                </dd>
              </div>
              <div class="flex items-start justify-between gap-4 p-4">
                <dt class="text-ink-gray-6 font-medium">
                  {{ __('Package') }}
                  <button
                    type="button"
                    class="ml-2 text-xs font-semibold text-[#bc1823] underline underline-offset-4 hover:text-[#a3141d]"
                    @click="stage = 'pricing'"
                  >
                    {{ __('Edit') }}
                  </button>
                </dt>
                <dd class="text-right font-semibold text-ink-gray-9">
                  <span
                    v-for="facility in chosenFacilities"
                    :key="facility.facility_id"
                    class="block"
                  >
                    {{ facility.facility_name || facility.mfl_code }} —
                    {{ selectedPackageFor(facility.facility_id)?.display_name || selectedPackageFor(facility.facility_id)?.item_code }}
                    <span class="block text-xs font-normal text-ink-gray-5 mt-0.5">
                      {{ money(selectedPackageFor(facility.facility_id)?.gross_total, selectedPackageFor(facility.facility_id)?.currency) }}
                      · {{ selectedPackageFor(facility.facility_id)?.token_quantity }} {{ __('tokens') }}
                    </span>
                  </span>
                </dd>
              </div>
              <div v-if="termsAccepted" class="flex items-center justify-between gap-4 p-4">
                <dt class="text-ink-gray-6 font-medium">
                  {{ __('Customer Experience email') }}
                </dt>
                <dd class="font-semibold text-ink-gray-9" data-testid="verified-account-email">
                  {{ accountEmail }}
                </dd>
              </div>
              <div class="flex items-center justify-between gap-4 p-4">
                <dt class="text-ink-gray-6 font-medium">{{ __('Terms') }}</dt>
                <dd class="text-right font-semibold text-ink-gray-9">
                  {{ termsSnapshot?.document }}
                </dd>
              </div>
            </dl>

            <div
              v-if="!catalog.network?.name"
              class="mt-5 rounded-xl border border-amber-200 bg-amber-50/90 p-4 text-sm leading-6 text-amber-900"
              role="status"
              data-testid="network-blocker"
            >
              <p>
                {{
                  __('We could not resolve a Network from the configured default. Enter the referring partner’s Network ID to continue.')
                }}
              </p>
              <button
                type="button"
                class="mt-2 font-bold underline underline-offset-4 text-amber-950"
                @click="stage = 'pricing'"
              >
                {{ __('Edit Partner Network ID') }}
              </button>
            </div>

            <section
              class="mt-6 rounded-xl border border-outline-gray-2 bg-surface-gray-1/60 p-5"
              aria-labelledby="review-terms-title"
              data-testid="self-onboarding-terms"
            >
              <div class="flex flex-wrap items-center justify-between gap-3">
                <h2 id="review-terms-title" class="text-sm font-semibold text-ink-gray-9">
                  {{ termsSnapshot?.document || __('Terms and Conditions') }}
                </h2>
                <button
                  type="button"
                  class="inline-flex items-center gap-1 text-xs font-semibold text-[#bc1823] underline underline-offset-4 hover:text-[#a3141d]"
                  aria-haspopup="dialog"
                  @click="termsDialogOpen = true"
                >
                  <span>{{ __('Read the complete Terms') }}</span>
                  <span>↗</span>
                </button>
              </div>
              <label class="mt-4 flex items-start gap-3 text-sm leading-6 text-ink-gray-8 cursor-pointer">
                <input
                  v-model="termsAccepted"
                  required
                  :disabled="!termsSnapshot?.content_hash"
                  type="checkbox"
                  class="mt-1 size-5 rounded border-outline-gray-2 text-[#bc1823] accent-[#bc1823] focus:ring-[#bc1823]/20"
                  data-testid="terms-acceptance"
                />
                <span class="font-medium">
                  {{ __('I have read and accept these Terms and Conditions.') }}
                </span>
              </label>
              <p
                v-if="!accountEmail"
                class="mt-3 rounded-xl bg-amber-100/70 p-3 text-xs leading-5 text-amber-900"
                role="alert"
              >
                {{ __('No email is available on your verified registry profile for Customer Experience access. Contact support to continue.') }}
              </p>
            </section>

            <dl
              v-if="totals"
              class="mt-6 space-y-2.5 rounded-xl border border-outline-gray-2 bg-white p-5 text-sm"
            >
              <div class="flex justify-between gap-4 text-ink-gray-6">
                <dt>
                  {{ __('Price excl. VAT') }}
                </dt>
                <dd class="font-medium text-ink-gray-9">
                  {{ money(totals.exVat, totals.currency) }}
                </dd>
              </div>
              <div class="flex justify-between gap-4 text-ink-gray-6">
                <dt>{{ totals.vatLabel }}</dt>
                <dd class="font-medium text-ink-gray-9">
                  {{ money(totals.vat, totals.currency) }}
                </dd>
              </div>
              <div class="flex justify-between gap-4 border-t border-outline-gray-2/70 pt-3 text-base">
                <dt class="font-semibold text-ink-gray-9">{{ __('Total incl. VAT') }}</dt>
                <dd class="font-semibold text-ink-gray-9 text-lg">
                  {{ money(totals.gross, totals.currency) }}
                </dd>
              </div>
            </dl>
          </div>
          <button
            :disabled="busy || !reviewReady"
            class="flex min-h-12 w-full items-center justify-center gap-2 rounded-xl px-6 text-sm font-semibold transition-all shadow-sm"
            :class="
              busy || !reviewReady
                ? 'bg-surface-gray-3 text-ink-gray-5 border border-outline-gray-3 cursor-not-allowed shadow-none'
                : 'bg-[#bc1823] text-white hover:bg-[#a3141d]'
            "
          >
            <span>{{
              busy ? __('Submitting…') : __('Submit facility onboarding')
            }}</span>
            <span v-if="!busy" class="text-base">→</span>
          </button>
          <button
            type="button"
            :disabled="busy"
            class="min-h-11 w-full text-sm font-semibold text-ink-gray-6 hover:text-ink-gray-9 transition"
            @click="goBack"
          >
            {{ __('Back to package') }}
          </button>
        </form>
        <section
          v-else
          class="rounded-2xl border border-outline-gray-2 bg-white/95 p-8 text-center shadow-sm backdrop-blur sm:p-12"
        >
          <div
            class="mx-auto flex size-16 items-center justify-center rounded-2xl bg-emerald-100 text-3xl font-bold text-emerald-700 ring-8 ring-emerald-50 mb-6"
          >
            ✓
          </div>
          <h2 class="text-2xl sm:text-3xl font-semibold text-ink-gray-9 tracking-tight">
            {{ __('Your onboarding has started') }}
          </h2>
          <p class="mx-auto mt-3 max-w-xl text-sm leading-6 text-ink-gray-6">
            {{
              portalStatus === 'linked'
                ? __(
                    'Your selected facilities have been added to your existing Customer Experience account. Sign in with your existing credentials to view them.',
                  )
                : __(
                    'We created your customer account and linked the selected facilities to the Network. Check this email for password setup instructions, then sign in to your portal to view your facilities.',
                  )
            }}
          </p>
          <p
            v-if="accountEmail"
            class="mx-auto mt-4 inline-flex items-center gap-2 rounded-full bg-surface-gray-2 border border-outline-gray-2 px-4 py-1.5 text-xs font-semibold text-ink-gray-8"
            data-testid="success-account-email"
          >
            <span class="text-ink-gray-4">✉</span>
            <span>{{ __('Customer Experience login: {0}', [accountEmail]) }}</span>
          </p>
          <div class="mx-auto mt-8 max-w-lg space-y-2.5 text-left">
            <div
              v-for="item in submissions"
              :key="item.mfl_code"
              class="flex items-center justify-between gap-4 rounded-xl border border-outline-gray-2 bg-surface-gray-1/70 px-4 py-3 text-sm shadow-sm"
            >
              <span class="font-semibold text-ink-gray-9">{{ item.facility }}</span>
              <span class="rounded bg-white px-2 py-0.5 font-mono text-xs font-semibold text-ink-gray-7 border border-outline-gray-2">
                {{ item.mfl_code }}
              </span>
            </div>
          </div>
          <a
            href="/login?redirect-to=/cx-portal"
            class="mt-9 inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-[#bc1823] px-8 text-sm font-semibold text-white shadow-sm transition-all hover:bg-[#a3141d]"
          >
            <span>{{ __('Go to sign in') }}</span>
            <span class="text-base">→</span>
          </a>
        </section>
      </section>
      <Dialog
        v-model:open="termsDialogOpen"
        :title="termsSnapshot?.document || __('Terms and Conditions')"
        :size="'4xl'"
      >
        <div
          v-if="termsSnapshot?.rendered_html"
          class="prose prose-sm max-w-none max-h-[70vh] overflow-y-auto"
          v-html="termsSnapshot.rendered_html"
        />
      </Dialog>
    </div>
  </main>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { call, Dialog } from 'frappe-ui'
import OtpCodeInput from '@/components/FacilityOnboarding/OtpCodeInput.vue'
import {
  STEPS,
  canAdvance,
  canResendOtp,
  deliveryState,
  formatCountdown,
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
const catalogError = ref('')
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
const packageSelections = ref({})
const accountEmail = ref('')
const termsAccepted = ref(false)
const termsSnapshot = ref(null)
const termsBusy = ref(false)
const termsDialogOpen = ref(false)
const submissions = ref([])
const portalStatus = ref('')
const delivery = ref({})
const resendIn = ref(0)
const otpError = ref('')
const sessionExpired = ref(false)
const registrationConflictDetected = ref(false)
const hfrRetryPending = ref(false)
const hfrRetryExhausted = ref(false)
let resendTimer = null
let catalogRequestId = 0
let loadedCatalogPartnerId = null
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
const allPackagesSelected = computed(
  () =>
    chosenFacilities.value.length > 0 &&
    chosenFacilities.value.every((facility) =>
      catalog.value.packages.some(
        (item) => item.item_code === packageSelections.value[facility.facility_id],
      ),
    ),
)
const totals = computed(() => {
  const packages = chosenFacilities.value.map((facility) =>
    selectedPackageFor(facility.facility_id),
  )
  if (!allPackagesSelected.value || packages.some((item) => !item)) return null
  const currency = packages[0]?.currency || 'KES'
  if (packages.some((item) => (item.currency || 'KES') !== currency)) return null
  return packages.reduce(
    (sum, item) => ({
      currency,
      vatLabel: item.vat_label || sum.vatLabel || 'VAT',
      exVat: sum.exVat + Number(item.price_ex_vat ?? item.price ?? 0),
      vat: sum.vat + Number(item.vat_amount || 0),
      gross: sum.gross + Number(item.gross_total ?? item.price_ex_vat ?? item.price ?? 0),
      count: sum.count + 1,
    }),
    { currency, vatLabel: '', exVat: 0, vat: 0, gross: 0, count: 0 },
  )
})
const reviewReady = computed(
  () =>
    Boolean(termsSnapshot.value?.content_hash) &&
    Boolean(catalog.value.network?.name) &&
    canAdvance('review', {
      accountEmail: accountEmail.value,
      hasNetwork: Boolean(catalog.value.network?.name),
      packageSelectionsComplete: allPackagesSelected.value,
      hasTerms: Boolean(termsSnapshot.value?.content_hash),
      termsAccepted: termsAccepted.value,
    }),
)
const networkName = computed(() => catalog.value.network?.display_name || '')
const supportEmail = computed(() => catalog.value.network?.contact_email || '')
const catalogCurrent = computed(
  () => loadedCatalogPartnerId === partnerId.value && Boolean(catalog.value.network),
)
function selectedPackageFor(facilityId) {
  return catalog.value.packages.find(
    (item) => item.item_code === packageSelections.value[facilityId],
  )
}
function packageMetadata(pkg) {
  if (!pkg) return { features: [], audience: '', badge: '' }
  let metrics = {}
  if (typeof pkg.coverage_metrics === 'string') {
    try {
      metrics = JSON.parse(pkg.coverage_metrics || '{}')
    } catch {
      metrics = {}
    }
  } else if (typeof pkg.coverage_metrics === 'object' && pkg.coverage_metrics) {
    metrics = pkg.coverage_metrics
  }
  const isFree = Number(pkg.price_ex_vat ?? pkg.price ?? 0) === 0
  const defaultFeatures = isFree
    ? [
        `${pkg.token_quantity || 25} Care Tokens included`,
        'Digital Registry & HFR Verification',
        'Routine Patient Encounters',
        'Community Support',
      ]
    : [
        `${pkg.token_quantity || 100} Care Tokens included`,
        pkg.coverage_summary || 'Standard clinical operations',
        'Outpatient Vitals & Consultations',
        'Priority Technical Support',
      ]
  const features = Array.isArray(metrics.features) && metrics.features.length
    ? metrics.features
    : defaultFeatures
  return {
    audience: metrics.audience || (isFree ? __('For individuals & community clinics') : __('For healthcare facilities & active clinics')),
    badge: metrics.badge || (isFree ? __('Free Forever') : (pkg.item_code?.includes('CORE') || pkg.display_name === 'Pro' ? __('Popular') : (pkg.item_code?.includes('PLUS') || pkg.display_name === 'Enterprise' ? __('Enterprise') : ''))),
    features,
  }
}
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
    description: __('Track your progress in the portal through launch.'),
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
const stepSubtitles = computed(() => ({
  identity: __('Verify owner'),
  facilities: __('Select clinics'),
  pricing: __('Choose plan'),
  review: __('Terms & submit'),
}))

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
onMounted(() => {
  if (stage.value === 'pricing') loadCatalog()
})
onBeforeUnmount(() => {
  stopResendTimer()
  catalogRequestId += 1
})
async function startIdentity() {
  errorMessage.value = ''
  sessionExpired.value = false
  termsSnapshot.value = null
  termsAccepted.value = false
  accountEmail.value = ''
  identityPreview.value = {}
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
  accountEmail.value = data.account_email || ''
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
  accountEmail.value = ''
  identityPreview.value = {}
  errorMessage.value = ''
  stage.value = 'identity'
}
function goBack() {
  const previous = previousStage(stage.value)
  if (previous) stage.value = previous
}
function continueFacilities() {
  if (selectedFacilities.value.length) {
    packageSelections.value = Object.fromEntries(
      Object.entries(packageSelections.value).filter(([facilityId]) =>
        selectedFacilities.value.includes(facilityId),
      ),
    )
    stage.value = 'pricing'
    loadCatalog()
  }
}
async function loadCatalog(force = false) {
  const requestedPartnerId = partnerId.value
  if (!force && loadedCatalogPartnerId === requestedPartnerId) {
    packageSelections.value = Object.fromEntries(
      selectedFacilities.value.map((facilityId) => [
        facilityId,
        catalog.value.packages?.some(
          (item) => item.item_code === packageSelections.value[facilityId],
        )
          ? packageSelections.value[facilityId]
          : '',
      ]),
    )
    return true
  }
  const requestId = ++catalogRequestId
  catalogError.value = ''
  catalogBusy.value = true
  catalog.value = { network: null, packages: [] }
  try {
    const previousSelections = packageSelections.value
    const nextCatalog = await request('get_catalog', {
      partner_id: requestedPartnerId,
    })
    if (requestId !== catalogRequestId) return false
    catalog.value = nextCatalog
    loadedCatalogPartnerId = requestedPartnerId
    packageSelections.value = Object.fromEntries(
      selectedFacilities.value.map((facilityId) => {
        const previousCode = previousSelections[facilityId]
        const packageCode = catalog.value.packages?.some(
          (item) => item.item_code === previousCode,
        )
          ? previousCode
          : (catalog.value.packages?.length === 1 ? catalog.value.packages[0].item_code : '')
        return [facilityId, packageCode]
      }),
    )
    return true
  } catch (error) {
    if (requestId !== catalogRequestId) return false
    catalog.value = { network: null, packages: [] }
    loadedCatalogPartnerId = null
    catalogError.value =
      error?.messages?.[0] || __('That Network ID is not available.')
    return false
  } finally {
    if (requestId === catalogRequestId) catalogBusy.value = false
  }
}
function onPartnerIdInput(event) {
  const nextPartnerId = String(event?.target?.value || '')
    .replace(/\D/g, '')
    .slice(0, 6)
  if (nextPartnerId === partnerId.value) return
  partnerId.value = nextPartnerId
  catalogRequestId += 1
  catalogBusy.value = false
  catalogError.value = ''
  loadedCatalogPartnerId = null
  catalog.value = { network: null, packages: [] }
  packageSelections.value = {}
  if (!nextPartnerId || nextPartnerId.length === 6) loadCatalog(true)
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
  if (
    !allPackagesSelected.value ||
    termsBusy.value ||
    catalogBusy.value ||
    catalogError.value ||
    !catalogCurrent.value
  )
    return
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
      'An enrollment already exists for this verified identity. Sign in to your Customer Experience account or contact support for help.',
    )
  }
  if (result?.already_onboarded_facility_ids?.length) {
    const blocked = new Set(result.already_onboarded_facility_ids)
    const names = facilities.value
      .filter((facility) => blocked.has(facility.facility_id))
      .map((facility) => facility.facility_name || facility.mfl_code)
    facilities.value = facilities.value.map((facility) =>
      blocked.has(facility.facility_id)
        ? {
            ...facility,
            onboarding_blocked: true,
            onboarding_block_reason: 'already_onboarded',
          }
        : facility,
    )
    selectedFacilities.value = selectedFacilities.value.filter(
      (facilityId) => !blocked.has(facilityId),
    )
    stage.value = 'facilities'
    return `${__('Already onboarded and cannot be selected to proceed')}: ${names.join(', ')}`
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
    return `${__('One or more selected facilities are already linked to this Network')}${selectedNames}. ${__('Remove them from your selection and try again.')}`
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
      registrationConflictDetected.value = [
        'existing_identity',
        'facility_review',
      ].includes(conflict?.outcome)
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
      package_item_code: packageSelections.value[selectedFacilities.value[0]] || '',
      facility_package_items: JSON.stringify(
        Object.fromEntries(
          selectedFacilities.value.map((facilityId) => [
            facilityId,
            packageSelections.value[facilityId],
          ]),
        ),
      ),
      account_email: accountEmail.value,
      terms_accepted: termsAccepted.value ? 1 : 0,
      accepted_terms_hash: termsSnapshot.value.content_hash,
    })
    const submitConflict = conflictMessage(data)
    if (submitConflict) {
      errorMessage.value = submitConflict
      registrationConflictDetected.value = [
        'existing_identity',
        'facility_review',
      ].includes(data?.outcome)
      return
    }
    if (data?.outcome && data.outcome !== 'new') {
      errorMessage.value = __(
        'We could not verify this onboarding selection. Please try again.',
      )
      return
    }
    submissions.value = data.enrollments || []
    portalStatus.value = data.portal_status || ''
    stage.value = 'success'
  } catch (error) {
    sessionExpired.value = isSessionError(error)
    const message =
      error?.messages?.[0] ||
      __('We could not complete onboarding. Please try again.')
    if (/terms/i.test(message)) {
      const refreshed = await loadSelfOnboardingTerms()
      if (refreshed) stage.value = 'review'
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
  submissions.value = []
  portalStatus.value = ''
  catalog.value = { network: null, packages: [] }
  catalogRequestId += 1
  catalogBusy.value = false
  catalogError.value = ''
  loadedCatalogPartnerId = null
  packageSelections.value = {}
  termsSnapshot.value = null
  termsAccepted.value = false
  accountEmail.value = ''
}
</script>
