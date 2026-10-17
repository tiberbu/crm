<template>
  <main class="min-h-screen bg-[#f6f7f8] text-ink-gray-9 relative isolate">
    <div class="pointer-events-none fixed inset-0 -z-10 overflow-hidden" aria-hidden="true">
      <div class="absolute -top-40 right-1/4 h-96 w-96 rounded-full bg-[radial-gradient(circle,rgba(188,24,35,0.06)_0%,transparent_65%)] blur-2xl"></div>
      <div class="absolute top-1/2 -left-24 h-96 w-96 rounded-full bg-[radial-gradient(circle,rgba(16,185,129,0.05)_0%,transparent_65%)] blur-2xl"></div>
    </div>
    <header class="sticky top-0 z-30 border-b border-outline-gray-2 bg-white/80 backdrop-blur-md">
      <div
        class="mx-auto flex items-center justify-between px-3.5 sm:px-8 py-3 transition-all duration-300"
        :class="stage === 'pricing' ? 'max-w-[1520px]' : 'max-w-6xl'"
      >
        <div class="flex items-center gap-2.5 sm:gap-3">
          <div
            class="flex size-8 sm:size-9 items-center justify-center rounded-xl bg-[#bc1823] text-white font-semibold text-sm sm:text-base shadow-sm shrink-0"
          >
            T
          </div>
          <div>
            <p class="text-xs sm:text-sm font-semibold tracking-tight text-ink-gray-9 leading-tight">
              Tiberbu <span class="font-normal text-ink-gray-5 hidden xs:inline">Customer Experience</span>
            </p>
            <p class="text-[10px] sm:text-[11px] font-medium text-ink-gray-5 flex items-center gap-1.5 mt-0.5">
              <span class="inline-block size-1.5 rounded-full bg-emerald-500"></span>
              {{ __('Secure facility onboarding') }}
            </p>
          </div>
        </div>
        <div class="flex items-center gap-2 sm:gap-3 text-xs sm:text-sm">
          <a
            v-if="supportEmail"
            :href="`mailto:${supportEmail}`"
            class="inline-flex items-center gap-1.5 font-medium text-ink-gray-6 hover:text-ink-gray-9 transition"
          >
            <svg class="size-4 text-ink-gray-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 5.636l-3.536 3.536m0 5.656l3.536 3.536M9.172 9.172L5.636 5.636m3.536 9.192l-3.536 3.536M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-5 0a4 4 0 11-8 0 4 4 0 018 0z" />
            </svg>
            <span class="hidden md:inline">{{ __('Need help?') }}</span>
          </a>
          <a
            href="/login?redirect-to=/cx-portal"
            class="inline-flex items-center gap-1.5 rounded-xl border border-outline-gray-2 bg-white/90 px-3 py-1.5 font-medium text-ink-gray-7 shadow-sm transition hover:bg-surface-gray-1 hover:text-ink-gray-9 text-xs"
          >
            <span class="sm:hidden">{{ __('Sign in') }}</span>
            <span class="hidden sm:inline">{{ __('Already have access? Sign in') }}</span>
          </a>
        </div>
      </div>
    </header>
    <div
      class="mx-auto px-3.5 sm:px-6 lg:px-8 py-5 sm:py-8 lg:py-10 transition-all duration-300"
      :class="stage === 'pricing' ? 'max-w-[1520px]' : 'max-w-6xl'"
    >
      <section
        v-if="stage === 'welcome'"
        class="grid gap-8 lg:gap-10 lg:grid-cols-[1.08fr_.92fr] lg:items-center"
      >
        <div>
          <span
            class="inline-flex items-center gap-1.5 rounded-full border border-[#f0d6d8] bg-[#fdf2f3] px-3 py-1 text-xs font-semibold uppercase tracking-wider text-[#bc1823]"
          >
            <span class="size-1.5 rounded-full bg-[#bc1823]"></span>
            {{ __('Start your facility journey') }}
          </span>
          <h1
            class="mt-4 max-w-2xl text-3xl font-semibold leading-tight tracking-tight text-ink-gray-9 sm:text-5xl lg:text-6xl"
          >
            {{
              networkName
                ? `Onboard ${facilityName || 'your facility'} with ${networkName}.`
                : __('Onboard your facility securely.')
            }}
          </h1>
          <p
            class="mt-4 sm:mt-5 max-w-xl text-sm sm:text-base leading-6 sm:leading-7 text-ink-gray-6"
          >
            {{
              __(
                'Verify your identity, select your facilities and token package, accept the Terms, and get secure Customer Experience access.',
              )
            }}
          </p>
          <div class="mt-6 sm:mt-8 flex flex-wrap items-center gap-4">
            <button
              class="inline-flex min-h-12 w-full sm:w-auto justify-center items-center gap-2 rounded-xl bg-[#bc1823] px-7 text-sm font-semibold text-white shadow-sm transition-all hover:bg-[#a3141d]"
              @click="stage = 'identity'"
            >
              <span>{{ __('Start secure onboarding') }}</span>
              <span class="text-lg">→</span>
            </button>
          </div>
          <p class="mt-3 text-xs font-medium text-ink-gray-5">
            {{ __('Usually 5–10 minutes · all displayed prices exclude VAT') }}
          </p>
        </div>
        <aside
          class="rounded-2xl border border-outline-gray-2 bg-white/90 p-4 sm:p-8 shadow-sm backdrop-blur-md"
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
      <!-- Interactive Sizing Calculator on Landing Page -->
      <section
        v-if="stage === 'welcome'"
        class="mt-10 sm:mt-12"
        aria-labelledby="calculator-landing-title"
      >
        <div class="max-w-2xl mx-auto text-center mb-6 sm:mb-8">
          <span
            class="inline-flex items-center gap-1.5 rounded-full border border-[#f0d6d8] bg-[#fdf2f3] px-3 py-1 text-xs font-semibold uppercase tracking-wider text-[#bc1823]"
          >
            <span class="size-1.5 rounded-full bg-[#bc1823]"></span>
            {{ __('Plan Sizing & Estimation') }}
          </span>
          <h2
            id="calculator-landing-title"
            class="mt-3 text-2xl sm:text-3xl font-bold tracking-tight text-ink-gray-9"
          >
            {{ __('Find the right token package for your facility') }}
          </h2>
          <p class="mt-2 text-xs sm:text-sm text-ink-gray-6 leading-relaxed">
            {{
              __(
                'Estimate monthly token requirements based on your patient encounters and clinical services. Select your ideal plan and jump straight into onboarding.',
              )
            }}
          </p>
        </div>

        <TokenCalculator
          :packages="catalog.packages"
          :config="catalog.calculator_config"
          :selected-package-code="landingPreselectedPackageCode"
          context="landing"
          @start-onboarding="startWithSelectedPlan"
          @select-package="(code) => (landingPreselectedPackageCode = code)"
        />
      </section>
      <section
        v-if="stage === 'welcome'"
        class="mt-8 rounded-2xl border border-outline-gray-2 bg-white/90 p-6 shadow-sm sm:p-8 backdrop-blur-md"
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
      <section v-else :class="stage === 'pricing' ? 'w-full' : 'mx-auto max-w-3xl'">
        <div
          class="mb-4 flex flex-wrap items-center justify-between gap-2.5 sm:gap-3"
          :class="stage === 'pricing' ? 'max-w-4xl mx-auto' : ''"
        >
          <div>
            <span
              class="inline-flex items-center gap-1.5 rounded-full border border-[#f0d6d8] bg-[#fdf2f3] px-2.5 py-0.5 text-[10px] sm:text-[11px] font-semibold uppercase tracking-wider text-[#bc1823]"
            >
              <span class="size-1.5 rounded-full bg-[#bc1823]"></span>
              {{ __('Facility onboarding') }}
            </span>
            <h1 class="mt-1 text-xl sm:text-2xl font-bold tracking-tight text-ink-gray-9 lg:text-3xl">
              {{ stageTitle }}
            </h1>
          </div>
          <button
            v-if="stage !== 'success'"
            type="button"
            class="inline-flex items-center gap-1.5 rounded-xl border border-outline-gray-2 bg-white px-3 py-1.5 text-xs font-semibold text-ink-gray-6 shadow-sm transition hover:bg-surface-gray-1 hover:text-ink-gray-9"
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
          class="mb-5 sm:mb-6 grid grid-cols-4 gap-1.5 sm:gap-4 rounded-xl border border-outline-gray-2 bg-white/85 p-2 sm:p-3 shadow-xs backdrop-blur-md"
          :class="stage === 'pricing' ? 'max-w-4xl mx-auto' : ''"
          :aria-label="__('Onboarding steps')"
        >
          <li
            v-for="(item, index) in progressSteps"
            :key="item.key"
            class="relative flex flex-col items-center sm:items-start transition-all"
            :aria-current="item.status === 'current' ? 'step' : undefined"
          >
            <div class="flex items-center w-full mb-1.5 sm:mb-2 justify-center sm:justify-start">
              <span
                class="flex size-6 sm:size-8 items-center justify-center rounded-lg sm:rounded-xl text-[11px] sm:text-xs font-bold transition-all duration-200 shrink-0"
                :class="
                  item.status === 'complete'
                    ? 'bg-emerald-600 text-white shadow-sm ring-2 sm:ring-4 ring-emerald-100'
                    : item.status === 'current'
                      ? 'bg-[#bc1823] text-white shadow-sm ring-2 sm:ring-4 ring-[#bc1823]/20'
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
                class="block truncate text-[11px] sm:text-sm font-semibold tracking-tight transition-colors"
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
              <span class="hidden md:block truncate text-[11px] font-normal transition-colors"
                :class="item.status === 'current' ? 'text-[#bc1823]/80 font-medium' : 'text-ink-gray-6'"
              >
                {{ stepSubtitles[item.key] }}
              </span>
            </div>
          </li>
        </ol>
        <div
          v-if="errorMessage"
          class="mb-5 sm:mb-6 flex flex-wrap items-center justify-between gap-2.5 sm:gap-3 rounded-2xl border border-rose-200 bg-rose-50/90 p-3.5 sm:p-4 text-xs sm:text-sm text-rose-900 shadow-sm backdrop-blur"
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
          class="rounded-2xl border border-outline-gray-2 bg-white/90 p-4 sm:p-9 shadow-sm backdrop-blur-md"
          @submit.prevent="startIdentity"
        >
          <div class="flex items-start gap-3 sm:gap-4">
            <div class="flex size-10 sm:size-12 shrink-0 items-center justify-center rounded-xl sm:rounded-2xl bg-[#fdf2f3] border border-[#f0d6d8] text-[#bc1823] shadow-sm">
              <svg class="size-5 sm:size-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <div>
              <h2 class="text-base sm:text-lg font-semibold text-ink-gray-9">
                {{ __('Verify Facility Ownership') }}
              </h2>
              <p class="mt-1 text-xs sm:text-sm leading-5 sm:leading-6 text-ink-gray-6">
                {{
                  __(
                    'Enter the ID used to register as the facility owner. We will check the registered contact first and look up facility details after you verify the code.',
                  )
                }}
              </p>
            </div>
          </div>

          <div class="mt-6 sm:mt-8 space-y-5 sm:space-y-6">
            <div>
              <label class="block text-xs font-semibold uppercase tracking-wider text-ink-gray-7">
                {{ __('Identification type') }}
              </label>
              <div class="relative mt-2">
                <select
                  v-model="identityType"
                  class="block w-full rounded-xl border border-outline-gray-2 bg-white px-3.5 sm:px-4 py-2.5 sm:py-3 text-base sm:text-sm font-medium text-ink-gray-9 shadow-sm transition focus:border-[#bc1823] focus:outline-none focus:ring-4 focus:ring-[#bc1823]/10"
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
                  class="block w-full rounded-xl border border-outline-gray-2 bg-white pl-10 sm:pl-11 pr-3.5 sm:pr-4 py-2.5 sm:py-3 text-base sm:text-sm font-medium text-ink-gray-9 placeholder:text-ink-gray-5 shadow-sm transition focus:border-[#bc1823] focus:outline-none focus:ring-4 focus:ring-[#bc1823]/10"
                  :placeholder="__('Enter your ID number')"
                />
              </div>
            </div>
          </div>

          <button
            :disabled="busy"
            class="mt-6 sm:mt-8 flex min-h-12 w-full items-center justify-center gap-2 rounded-xl px-6 text-sm font-semibold transition-all shadow-sm"
            :class="
              busy
                ? 'bg-surface-gray-3 text-ink-gray-5 border border-outline-gray-3 cursor-not-allowed shadow-none'
                : 'bg-[#bc1823] text-white hover:bg-[#a3141d]'
            "
          >
            <span>{{ busy ? __('Checking…') : __('Find my facilities') }}</span>
            <span v-if="!busy" class="text-base">→</span>
          </button>
          <div class="mt-4 sm:mt-5 flex items-center justify-center gap-2 text-center text-[11px] sm:text-xs text-ink-gray-7 font-medium leading-normal">
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
          class="rounded-2xl border border-outline-gray-2 bg-white/90 p-4 sm:p-9 shadow-sm backdrop-blur-md"
          @submit.prevent="verifyOtp"
        >
          <div
            v-if="hfrRetryPending"
            class="rounded-xl border border-amber-200 bg-amber-50/90 p-4 sm:p-5 text-xs sm:text-sm leading-5 sm:leading-6 text-amber-900 shadow-sm"
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
              class="rounded-xl border border-amber-200 bg-amber-50/90 p-4 text-xs sm:text-sm leading-5 sm:leading-6 text-amber-900"
              role="status"
            >
              {{
                __(
                  'We could not deliver a code just now. Retry delivery to this verified contact session.',
                )
              }}
            </div>
            <div v-else class="text-center" role="status">
              <div class="mx-auto flex size-10 sm:size-12 items-center justify-center rounded-xl sm:rounded-2xl bg-[#fdf2f3] border border-[#f0d6d8] text-[#bc1823] shadow-sm mb-3 sm:mb-4">
                <svg class="size-5 sm:size-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
                </svg>
              </div>
              <h2 class="text-base sm:text-lg font-semibold text-ink-gray-9">
                {{ __('Enter Verification Code') }}
              </h2>
              <p class="mx-auto mt-1.5 sm:mt-2 max-w-md text-xs sm:text-sm leading-5 sm:leading-6 text-ink-gray-6">
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
              <div class="mt-2 inline-flex items-center gap-1.5 rounded-full bg-surface-gray-2 border border-outline-gray-3 px-2.5 sm:px-3 py-0.5 sm:py-1 text-[11px] sm:text-xs font-semibold text-ink-gray-7">
                <svg class="size-3.5 text-ink-gray-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>{{ __('The code expires in {0} minutes.', [expiryMinutes]) }}</span>
              </div>
            </div>
            <div class="mt-6 sm:mt-8">
              <OtpCodeInput
                v-model="otp"
                :disabled="busy"
                :error="otpError"
                :label="__('Verification code')"
              />
            </div>
            <button
              :disabled="busy || otp.length !== 6"
              class="mt-6 sm:mt-8 flex min-h-12 w-full items-center justify-center gap-2 rounded-xl px-6 text-sm font-semibold transition-all shadow-sm"
              :class="
                busy || otp.length !== 6
                  ? 'bg-surface-gray-3 text-ink-gray-5 border border-outline-gray-3 cursor-not-allowed shadow-none'
                  : 'bg-[#bc1823] text-white hover:bg-[#a3141d]'
              "
            >
              <span>{{ busy ? __('Verifying…') : __('Verify and continue') }}</span>
              <span v-if="!busy" class="text-base">→</span>
            </button>
            <div class="mt-4 flex flex-col gap-2 sm:flex-row sm:justify-between items-stretch sm:items-center">
              <button
                type="button"
                :disabled="!canResendOtp(delivery, resendIn, busy)"
                class="min-h-11 w-full sm:w-auto text-center rounded-xl px-4 text-xs font-semibold text-[#bc1823] hover:text-[#a3141d] hover:bg-[#fdf2f3] disabled:text-ink-gray-5 disabled:hover:bg-transparent transition"
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
                class="min-h-11 w-full sm:w-auto text-center rounded-xl px-4 text-xs font-semibold text-ink-gray-6 hover:text-ink-gray-9 hover:bg-surface-gray-1 disabled:text-ink-gray-5 disabled:hover:bg-transparent transition"
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
            class="rounded-2xl border border-outline-gray-2 bg-white/90 p-4 sm:p-9 shadow-sm backdrop-blur-md"
          >
            <section
              v-if="
                identityPreview.full_name ||
                identityPreview.email ||
                identityPreview.phone
              "
              class="mb-6 sm:mb-7 rounded-xl sm:rounded-2xl border-2 border-[#f0d6d8] bg-[#fdf2f3] p-4 sm:p-5 shadow-sm"
              :aria-label="__('Verified identity')"
            >
              <div class="flex items-center gap-3 sm:gap-3.5">
                <div class="flex size-9 sm:size-10 shrink-0 items-center justify-center rounded-xl bg-emerald-600 text-white font-bold text-sm sm:text-base shadow-sm ring-2 sm:ring-4 ring-emerald-100">
                  ✓
                </div>
                <div>
                  <div class="flex items-center gap-2">
                    <h2 class="text-xs sm:text-sm font-bold text-ink-gray-9">
                      {{ __('Verified identity') }}
                    </h2>
                    <span class="rounded-full bg-white border border-[#bc1823]/30 px-2 py-0.5 text-[10px] font-bold text-[#bc1823] uppercase tracking-wide">
                      {{ __('Registry Verified') }}
                    </span>
                  </div>
                  <p
                    v-if="identityPreview.full_name"
                    class="mt-0.5 text-sm sm:text-lg font-bold text-ink-gray-9"
                  >
                    {{ identityPreview.full_name }}
                  </p>
                </div>
              </div>
              <div class="mt-3.5 sm:mt-4 grid gap-1.5 sm:gap-2 border-t border-[#f0d6d8] pt-3 text-[11px] sm:text-xs grid-cols-1 sm:grid-cols-2">
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
              <h3 class="text-sm sm:text-base font-semibold text-ink-gray-9">
                {{ __('Select facilities to onboard') }}
              </h3>
              <p class="mt-1 text-xs sm:text-sm leading-5 sm:leading-6 text-ink-gray-7">
                {{
                  __(
                    'Select all eligible facilities you want to add under the same Opt-In Network.',
                  )
                }}
              </p>
            </div>

            <p
              v-if="!facilities.length"
              class="mt-6 rounded-2xl border border-outline-gray-2 bg-surface-gray-1 p-4 sm:p-5 text-xs sm:text-sm leading-5 sm:leading-6 text-ink-gray-7"
              role="status"
            >
              {{
                __(
                  'No eligible facilities were returned for this verified identity. Contact support if you think this is an error.',
                )
              }}
            </p>
            <div class="mt-5 sm:mt-6 space-y-3 sm:space-y-3.5">
              <label
                v-for="facility in facilities"
                :key="facility.facility_id"
                class="flex gap-3 sm:gap-4 rounded-xl sm:rounded-2xl border p-3.5 sm:p-5 transition-all"
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
                  class="mt-0.5 sm:mt-1 size-5 shrink-0 rounded border-outline-gray-2 text-[#bc1823] accent-[#bc1823] focus:ring-[#bc1823]/20 disabled:cursor-not-allowed disabled:opacity-40"
                />
                <div class="min-w-0 flex-1">
                  <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-1 sm:gap-2">
                    <strong class="text-sm sm:text-base font-bold text-ink-gray-9">
                      {{ facility.facility_name || facility.mfl_code }}
                    </strong>
                    <span
                      v-if="facility.facility_level || facility.classification"
                      class="self-start sm:self-auto inline-flex items-center rounded-full bg-surface-gray-2 border border-outline-gray-3 px-2 py-0.5 text-[10px] sm:text-xs font-semibold text-ink-gray-8"
                    >
                      {{ facility.facility_level || facility.classification }}
                    </span>
                  </div>
                  <div class="mt-1.5 flex flex-wrap items-center gap-1.5 sm:gap-2 text-[11px] sm:text-xs">
                    <span class="font-semibold text-ink-gray-8">{{ facility.facility_type || __('Facility') }}</span>
                    <span class="text-ink-gray-4">·</span>
                    <span class="text-ink-gray-7">{{ facility.classification || __('Classification pending') }}</span>
                    <span class="text-ink-gray-4">·</span>
                    <span class="rounded bg-white px-1.5 py-0.5 font-mono text-[10px] sm:text-[11px] font-bold text-ink-gray-9 border border-outline-gray-3">
                      {{ facility.mfl_code }}
                    </span>
                  </div>
                  <span
                    v-if="facility.onboarding_blocked"
                    class="mt-2.5 sm:mt-3 inline-flex items-center gap-1.5 rounded-lg bg-rose-50 border border-rose-200 px-2.5 py-1 sm:px-3 sm:py-1.5 text-xs font-bold text-rose-800"
                    data-testid="facility-already-onboarded"
                  >
                    <svg class="size-4 shrink-0 text-rose-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    {{ __('Already onboarded. This facility cannot be selected to proceed.') }}
                  </span>
                  <span
                    v-else-if="facility.onboarding_eligible !== true"
                    class="mt-2.5 sm:mt-3 inline-flex items-center gap-1.5 rounded-lg bg-amber-50 border border-amber-200 px-2.5 py-1 sm:px-3 sm:py-1.5 text-xs font-bold text-amber-900"
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
          <!-- Sizing Calculator Dialog -->
          <Dialog
            v-model:open="calculatorDialogOpen"
            :title="__('CareVerse Token Sizing Calculator')"
            size="5xl"
          >
            <div class="p-1 sm:p-2 max-h-[85vh] sm:max-h-[80vh] overflow-y-auto">
              <TokenCalculator
                v-if="activePricingFacility"
                :packages="catalog.packages"
                :config="catalog.calculator_config"
                :selected-package-code="packageSelections[activePricingFacility.facility_id]"
                :facility-name="activePricingFacility.facility_name || activePricingFacility.mfl_code"
                context="onboarding"
                @select-package="onCalculatorSelectPackage"
                @apply-plan="onCalculatorApplyPlan"
              />
            </div>
          </Dialog>

          <div
            class="rounded-2xl border border-outline-gray-2 bg-white/95 p-3.5 sm:p-6 shadow-sm backdrop-blur-md"
          >
            <!-- Pricing Stage Control Bar: Facility context, Tabs, Calculator and Referral -->
            <div class="space-y-3 pb-3 border-b border-outline-gray-2">
              <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                <!-- Facility Context / Switcher -->
                <div class="flex items-center gap-2 flex-wrap">
                  <!-- Single Facility Mode -->
                  <div
                    v-if="chosenFacilities.length === 1 && activePricingFacility"
                    class="inline-flex items-center gap-2 rounded-xl border border-outline-gray-2 bg-surface-gray-2 px-3 py-1 text-xs font-semibold text-ink-gray-8"
                  >
                    <span>🏥</span>
                    <span class="font-bold text-ink-gray-9">{{ activePricingFacility.facility_name || activePricingFacility.mfl_code }}</span>
                    <span class="text-ink-gray-5 font-normal">({{ activePricingFacility.classification || activePricingFacility.facility_level || __('Facility') }}<span v-if="activePricingFacility.mfl_code"> · MFL {{ activePricingFacility.mfl_code }}</span>)</span>
                  </div>

                  <!-- Multi-Facility Tabs Strip -->
                  <div
                    v-else-if="chosenFacilities.length > 1"
                    class="flex items-center gap-2 overflow-x-auto pb-1 max-w-full"
                    role="tablist"
                    :aria-label="__('Facilities')"
                  >
                    <button
                      v-for="facility in chosenFacilities"
                      :key="facility.facility_id"
                      type="button"
                      role="tab"
                      :aria-selected="activePricingFacility?.facility_id === facility.facility_id"
                      class="group relative flex shrink-0 items-center gap-1.5 sm:gap-2 rounded-xl px-2.5 sm:px-3 py-1.5 text-xs font-semibold transition-all border shadow-xs"
                      :class="activePricingFacility?.facility_id === facility.facility_id
                        ? 'border-2 border-[#bc1823] bg-[#fdf2f3] text-[#bc1823] ring-2 ring-[#bc1823]/10'
                        : 'border-outline-gray-2 bg-white text-ink-gray-7 hover:border-outline-gray-3 hover:text-ink-gray-9'"
                      @click="activePricingFacilityId = facility.facility_id"
                    >
                      <span
                        class="flex size-2 rounded-full shrink-0"
                        :class="packageSelections[facility.facility_id] ? 'bg-emerald-500' : 'bg-amber-400'"
                      ></span>
                      <span class="max-w-[130px] sm:max-w-[170px] truncate font-medium text-ink-gray-9 group-hover:text-[#bc1823]">
                        {{ facility.facility_name || facility.mfl_code }}
                      </span>
                      <span
                        v-if="packageSelections[facility.facility_id]"
                        class="rounded-full px-2 py-0.5 text-[10px] font-bold shrink-0"
                        :class="activePricingFacility?.facility_id === facility.facility_id
                          ? 'bg-[#bc1823] text-white'
                          : 'bg-surface-gray-2 text-ink-gray-7 border border-outline-gray-2'"
                      >
                        {{ selectedPackageFor(facility.facility_id)?.display_name || __('Selected') }}
                      </span>
                      <span
                        v-else
                        class="text-[10px] text-amber-600 font-normal italic shrink-0"
                      >
                        {{ __('Needs plan') }}
                      </span>
                    </button>
                  </div>

                  <!-- Network Badge (if available) -->
                  <span
                    v-if="catalog.network?.display_name"
                    class="inline-flex items-center gap-1.5 rounded-full border border-[#f0d6d8] bg-[#fdf2f3] px-2.5 py-0.5 text-xs font-semibold text-[#bc1823]"
                  >
                    <span class="size-1.5 rounded-full bg-emerald-500"></span>
                    {{ catalog.network.display_name }}
                  </span>
                </div>

                <!-- Action Triggers: Batch Apply & Calculator -->
                <div class="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 shrink-0 w-full md:w-auto">
                  <button
                    v-if="chosenFacilities.length > 1 && activePricingFacility && packageSelections[activePricingFacility.facility_id]"
                    type="button"
                    class="inline-flex shrink-0 items-center justify-center gap-1.5 text-xs font-semibold text-[#bc1823] hover:text-[#a3141d] bg-[#fdf2f3] hover:bg-[#fbdfe1] border border-[#f0d6d8] px-3 py-2 sm:py-1.5 rounded-xl transition shadow-2xs w-full sm:w-auto"
                    @click="applyCurrentPackageToAll"
                  >
                    <svg class="size-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                    <span>{{ __('Apply plan to all :n facilities', { n: chosenFacilities.length }).replace(':n', chosenFacilities.length) }}</span>
                  </button>

                  <button
                    type="button"
                    class="inline-flex items-center justify-center gap-1.5 rounded-xl border border-outline-gray-3 bg-white px-3 py-2 sm:py-1.5 text-xs font-bold text-ink-gray-8 shadow-xs transition hover:border-[#bc1823] hover:text-[#bc1823] hover:bg-[#fdf2f3] w-full sm:w-auto"
                    @click="calculatorDialogOpen = true"
                  >
                    <span>🧮</span>
                    <span>{{ __('Open Sizing Calculator') }}</span>
                    <span>→</span>
                  </button>
                </div>
              </div>

              <!-- Micro Info & Referral Line -->
              <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5 sm:gap-2 text-[11px] text-ink-gray-5 pt-0.5">
                <p>
                  {{ __('Choose the monthly token package for this facility. Displayed prices exclude 16% VAT.') }}
                </p>
                <details class="group relative self-start sm:self-auto">
                  <summary class="cursor-pointer font-medium text-ink-gray-6 hover:text-ink-gray-9 transition select-none flex items-center gap-1">
                    <span v-if="partnerId" class="text-[#bc1823] font-mono font-bold">Network ID: {{ partnerId }}</span>
                    <span v-else class="underline underline-offset-2">{{ __('Referred by a partner?') }}</span>
                  </summary>
                  <div class="absolute right-0 top-5 z-20 w-[calc(100vw-3rem)] max-w-xs sm:w-72 rounded-xl border border-outline-gray-2 bg-white p-3 shadow-xl text-left">
                    <label class="block text-[11px] font-bold uppercase tracking-wider text-ink-gray-7 mb-1">
                      {{ __('Partner Network ID (6 digits)') }}
                    </label>
                    <input
                      :value="partnerId"
                      inputmode="numeric"
                      autocomplete="off"
                      maxlength="6"
                      pattern="[0-9]{6}"
                      :aria-invalid="Boolean(partnerId && partnerId.length !== 6)"
                      :title="__('Enter all six digits or leave this field blank.')"
                      placeholder="123456"
                      class="block w-full rounded-lg border border-outline-gray-3 bg-white px-2.5 py-1.5 font-mono text-base sm:text-xs shadow-xs focus:border-[#bc1823] focus:outline-none focus:ring-2 focus:ring-[#bc1823]/10"
                      @input="onPartnerIdInput"
                    />
                    <p class="mt-1 text-[10px] text-ink-gray-5">
                      {{ __('Links to partner network. Leave blank to use Tiberbu’s default.') }}
                    </p>
                    <span
                      v-if="partnerId && partnerId.length !== 6"
                      class="mt-1 inline-flex items-center gap-1 text-[10px] font-semibold text-amber-700"
                    >
                      ⚠️ {{ __('Must be exactly 6 digits.') }}
                    </span>
                  </div>
                </details>
              </div>
            </div>

            <!-- Loading Spinner -->
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

            <!-- Skeleton Loaders -->
            <div
              v-if="catalogBusy"
              class="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
              aria-hidden="true"
            >
              <div
                v-for="placeholder in 4"
                :key="placeholder"
                class="animate-pulse rounded-2xl border border-outline-gray-2 bg-surface-gray-1 p-5 min-h-[360px]"
              >
                <div class="h-5 w-2/3 rounded-lg bg-surface-gray-2"></div>
                <div class="mt-4 h-7 w-1/2 rounded-lg bg-surface-gray-2"></div>
                <div class="mt-4 h-4 w-full rounded bg-surface-gray-2"></div>
                <div class="mt-6 h-12 w-full rounded-xl bg-surface-gray-2"></div>
              </div>
            </div>

            <!-- Error State -->
            <div
              v-else-if="catalogError"
              class="mt-6 rounded-2xl border border-rose-200 bg-rose-50/90 p-4 sm:p-5 text-xs sm:text-sm shadow-sm"
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

            <!-- Partner Incomplete State -->
            <div
              v-else-if="partnerId && partnerId.length !== 6"
              class="mt-6 rounded-2xl border border-outline-gray-2 bg-surface-gray-1 p-4 sm:p-5 text-xs sm:text-sm text-ink-gray-6"
              role="status"
              data-testid="catalog-partner-incomplete"
            >
              {{ __('Enter all six digits to load this Network’s packages, or clear the field to use the configured default.') }}
            </div>

            <!-- Empty Catalog State -->
            <div
              v-else-if="!catalog.packages?.length"
              class="mt-6 rounded-2xl border border-outline-gray-2 bg-surface-gray-1 p-5 sm:p-6 text-center text-xs sm:text-sm text-ink-gray-6"
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

            <!-- Active Facility Pricing Section with Wide, Viewport-Optimized 4-Card Grid -->
            <div
              v-else
              :data-testid="activePricingFacility ? `facility-package-${activePricingFacility.facility_id}` : undefined"
              class="mt-4"
            >
              <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4 items-stretch">
                <article
                  v-for="item in catalog.packages"
                  :key="`${activePricingFacility?.facility_id}-${item.item_code}`"
                  class="relative rounded-2xl border p-4 sm:p-5 flex flex-col justify-between transition-all duration-200 cursor-pointer shadow-xs group min-h-[auto] sm:min-h-[380px]"
                  :class="isPackageSelected(item.item_code)
                    ? 'border-2 border-[#bc1823] bg-[#fdf2f3]/25 ring-4 ring-[#bc1823]/10 shadow-md'
                    : (packageMetadata(item).isPopular
                      ? 'border-[#f0d6d8] bg-white hover:border-[#bc1823] hover:shadow-md'
                      : 'border-outline-gray-2 bg-white hover:border-outline-gray-3 hover:shadow-md')"
                  @click="selectPackageForActiveFacility(item.item_code)"
                >
                  <div>
                    <!-- Row 1: Title & Badge (Symmetrical h-7) -->
                    <div class="flex items-center justify-between gap-2 h-7">
                      <h4 class="text-base sm:text-lg font-bold text-ink-gray-9 tracking-tight truncate">
                        {{ item.display_name || item.item_code }}
                      </h4>
                      <span
                        v-if="packageMetadata(item).badge"
                        class="px-2.5 py-0.5 rounded-full text-[10px] font-bold tracking-wider uppercase shrink-0"
                        :class="packageMetadata(item).badgeClass"
                      >
                        {{ packageMetadata(item).badge }}
                      </span>
                    </div>

                    <!-- Row 2: Price & VAT Line (Symmetrical h-14) -->
                    <div class="mt-2 h-14 flex flex-col justify-center">
                      <div class="flex items-baseline gap-1.5 flex-wrap">
                        <span class="text-2xl sm:text-3xl font-extrabold tracking-tight text-ink-gray-9">
                          {{ money(item.price_ex_vat ?? item.price ?? 0, item.currency) }}
                        </span>
                        <span class="text-xs text-ink-gray-5 font-semibold">
                          {{ Number(item.price_ex_vat ?? item.price ?? 0) === 0 ? __('Zero commitment') : __('/ mo (excl. VAT)') }}
                        </span>
                      </div>
                      <p class="mt-0.5 text-[11px] text-ink-gray-5 font-medium truncate">
                        {{ Number(item.price_ex_vat ?? item.price ?? 0) === 0
                          ? __('100% Free · No credit card required')
                          : `${item.vat_label || 'VAT'} ${money(item.vat_amount, item.currency)} · Total ${money(item.gross_total, item.currency)}`
                        }}
                      </p>
                    </div>

                    <!-- Row 3: Audience Tagline (Symmetrical h-8) -->
                    <div class="mt-1 h-8 flex items-center">
                      <p class="text-xs text-ink-gray-6 font-medium leading-tight line-clamp-2">
                        {{ packageMetadata(item).audience }}
                      </p>
                    </div>

                    <!-- Row 4: Token & Capacity Chip (Symmetrical h-[64px]) -->
                    <div class="mt-2.5 rounded-xl bg-surface-gray-1 p-2.5 border border-outline-gray-2 h-[64px] flex flex-col justify-center">
                      <div class="flex items-center justify-between text-xs font-bold">
                        <span class="flex items-center gap-1.5 text-ink-gray-9 truncate">
                          <span class="text-amber-500 text-sm">🪙</span>
                          <span>{{ item.token_quantity?.toLocaleString() }} {{ __('Tokens') }}</span>
                        </span>
                        <span
                          v-if="packageMetadata(item).bonusLabel"
                          class="text-[10px] font-bold px-2 py-0.5 rounded-full border shrink-0"
                          :class="packageMetadata(item).bonusClass"
                        >
                          {{ packageMetadata(item).bonusLabel }}
                        </span>
                      </div>
                      <p class="mt-0.5 text-[11px] text-ink-gray-6 font-medium truncate">
                        {{ packageMetadata(item).capacityLabel }}
                      </p>
                    </div>

                    <!-- Row 5: 3 Clean Features (Symmetrical min-h-[80px]) -->
                    <div class="mt-2.5 pt-2.5 border-t border-outline-gray-1 min-h-[72px] sm:min-h-[80px]">
                      <ul class="space-y-1.5 text-xs text-ink-gray-7">
                        <li
                          v-for="feature in packageMetadata(item).features"
                          :key="feature"
                          class="flex items-start gap-2"
                        >
                          <svg class="size-3.5 text-emerald-600 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/>
                          </svg>
                          <span class="leading-tight font-medium text-ink-gray-8 truncate">{{ feature }}</span>
                        </li>
                      </ul>
                    </div>
                  </div>

                  <!-- Row 6: Selection Button (Anchored at Bottom of Card) -->
                  <div class="mt-3 pt-2">
                    <button
                      type="button"
                      class="w-full min-h-11 sm:min-h-9 py-2 px-4 rounded-xl text-xs font-bold transition-all duration-150 flex items-center justify-center gap-1.5"
                      :class="isPackageSelected(item.item_code)
                        ? 'bg-[#bc1823] text-white shadow-sm hover:bg-[#a3141d]'
                        : 'border border-outline-gray-3 text-ink-gray-9 bg-white hover:bg-[#fdf2f3] hover:text-[#bc1823] hover:border-[#f0d6d8]'"
                      @click.stop="selectPackageForActiveFacility(item.item_code)"
                    >
                      <span v-if="isPackageSelected(item.item_code)">✓</span>
                      <span>{{ isPackageSelected(item.item_code) ? __('Plan Selected') : __('Choose plan') }}</span>
                    </button>
                  </div>
                </article>
              </div>

              <!-- Hidden Radios for Form Submission / Accessibility / Testing -->
              <div class="sr-only" aria-hidden="true">
                <template v-for="facility in chosenFacilities" :key="facility.facility_id">
                  <input
                    v-for="item in catalog.packages"
                    :key="`${facility.facility_id}-${item.item_code}`"
                    v-model="packageSelections[facility.facility_id]"
                    type="radio"
                    :name="`package-${facility.facility_id}`"
                    :value="item.item_code"
                  />
                </template>
              </div>

              <!-- At-A-Glance Multi-Facility Summary Table (if > 1 facility) -->
              <div
                v-if="chosenFacilities.length > 1"
                class="mt-6 rounded-xl sm:rounded-2xl border border-outline-gray-2 bg-surface-gray-1/40 p-3.5 sm:p-5"
              >
                <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5 sm:gap-3 mb-3">
                  <div class="flex items-center gap-2">
                    <span class="text-xs sm:text-sm font-semibold text-ink-gray-9">{{ __('Facility Package Allocation') }}</span>
                    <span class="rounded-full bg-surface-gray-2 px-2 py-0.5 text-[10px] sm:text-[11px] font-medium text-ink-gray-7">
                      {{ chosenFacilities.length }} {{ __('facilities') }}
                    </span>
                  </div>
                  <span class="text-[11px] sm:text-xs text-ink-gray-5">
                    {{ __('Click any row to switch active facility') }}
                  </span>
                </div>

                <div class="overflow-x-auto -mx-1 sm:mx-0">
                  <table class="w-full min-w-[500px] text-left text-xs">
                    <thead>
                      <tr class="border-b border-outline-gray-2 text-[11px] font-semibold uppercase tracking-wider text-ink-gray-5">
                        <th class="py-2.5 pr-4">{{ __('Facility') }}</th>
                        <th class="py-2.5 px-4">{{ __('Selected Plan') }}</th>
                        <th class="py-2.5 px-4 text-center">{{ __('Tokens') }}</th>
                        <th class="py-2.5 pl-4 text-right">{{ __('Monthly Cost (excl. VAT)') }}</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-outline-gray-1">
                      <tr
                        v-for="facility in chosenFacilities"
                        :key="facility.facility_id"
                        class="cursor-pointer transition hover:bg-surface-gray-1"
                        :class="activePricingFacility?.facility_id === facility.facility_id ? 'bg-[#fdf2f3]/40 font-medium' : ''"
                        @click="activePricingFacilityId = facility.facility_id"
                      >
                        <td class="py-2.5 pr-4">
                          <div class="flex items-center gap-2">
                            <span
                              class="size-1.5 rounded-full"
                              :class="packageSelections[facility.facility_id] ? 'bg-emerald-500' : 'bg-amber-400'"
                            ></span>
                            <span class="text-ink-gray-9 font-medium">{{ facility.facility_name || facility.mfl_code }}</span>
                            <span
                              v-if="activePricingFacility?.facility_id === facility.facility_id"
                              class="text-[10px] text-[#bc1823] font-semibold uppercase"
                            >
                              ({{ __('Active') }})
                            </span>
                          </div>
                          <p class="text-[11px] text-ink-gray-5 pl-3.5">
                            {{ facility.classification || facility.facility_level || __('Facility') }}
                          </p>
                        </td>
                        <td class="py-2.5 px-4">
                          <span
                            v-if="selectedPackageFor(facility.facility_id)"
                            class="inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-semibold"
                            :class="Number(selectedPackageFor(facility.facility_id)?.price_ex_vat ?? selectedPackageFor(facility.facility_id)?.price ?? 0) === 0
                              ? 'bg-surface-gray-2 text-ink-gray-8'
                              : 'bg-[#fdf2f3] text-[#bc1823] border border-[#f0d6d8]'"
                          >
                            {{ selectedPackageFor(facility.facility_id)?.display_name }}
                          </span>
                          <span v-else class="text-amber-600 italic">{{ __('Needs package') }}</span>
                        </td>
                        <td class="py-2.5 px-4 text-center">
                          <span v-if="selectedPackageFor(facility.facility_id)" class="font-semibold text-ink-gray-9">
                            🪙 {{ selectedPackageFor(facility.facility_id)?.token_quantity?.toLocaleString() }}
                          </span>
                          <span v-else class="text-ink-gray-4">—</span>
                        </td>
                        <td class="py-2.5 pl-4 text-right font-medium text-ink-gray-9">
                          <span v-if="selectedPackageFor(facility.facility_id)">
                            {{ Number(selectedPackageFor(facility.facility_id)?.price_ex_vat ?? selectedPackageFor(facility.facility_id)?.price ?? 0) === 0
                              ? __('KES 0 (Free)')
                              : money(selectedPackageFor(facility.facility_id)?.price_ex_vat ?? selectedPackageFor(facility.facility_id)?.price, selectedPackageFor(facility.facility_id)?.currency)
                            }}
                          </span>
                          <span v-else class="text-ink-gray-4">—</span>
                        </td>
                      </tr>
                    </tbody>
                    <tfoot v-if="totals" class="border-t-2 border-outline-gray-2 font-semibold text-ink-gray-9">
                      <tr>
                        <td colspan="2" class="py-2.5 pr-4 text-xs font-bold uppercase tracking-wider text-ink-gray-6">
                          {{ __('Combined Monthly Commitment') }}
                        </td>
                        <td class="py-2.5 px-4 text-center">
                          🪙 {{ chosenFacilities.reduce((sum, f) => sum + (selectedPackageFor(f.facility_id)?.token_quantity || 0), 0).toLocaleString() }}
                        </td>
                        <td class="py-2.5 pl-4 text-right">
                          <div>{{ money(totals.exVat, totals.currency) }} <span class="text-[10px] font-normal text-ink-gray-5">excl. VAT</span></div>
                          <div v-if="totals.vat > 0" class="text-[11px] font-normal text-ink-gray-5">
                            + {{ totals.vatLabel }} {{ money(totals.vat, totals.currency) }} = <strong class="text-ink-gray-9 font-semibold">{{ money(totals.gross, totals.currency) }}</strong>
                          </div>
                        </td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </div>
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
            class="rounded-2xl border border-outline-gray-2 bg-white/90 p-4 sm:p-9 shadow-sm backdrop-blur-md"
          >
            <div class="flex items-center gap-3">
              <div class="flex size-9 sm:size-10 items-center justify-center rounded-xl bg-surface-gray-2 text-ink-gray-7 font-semibold text-sm">
                📋
              </div>
              <div>
                <h2 class="text-lg sm:text-xl font-semibold text-ink-gray-9">
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

            <dl class="mt-5 sm:mt-7 divide-y divide-outline-gray-2 rounded-xl border border-outline-gray-2 bg-surface-gray-1/50 text-xs sm:text-sm">
              <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5 sm:gap-4 p-3.5 sm:p-4">
                <dt class="text-ink-gray-6 font-medium flex items-center justify-between sm:justify-start">
                  <span>{{ __('Network') }}</span>
                  <button
                    type="button"
                    class="ml-2 text-xs font-semibold text-[#bc1823] underline underline-offset-4 hover:text-[#a3141d]"
                    @click="stage = 'pricing'"
                  >
                    {{ __('Edit') }}
                  </button>
                </dt>
                <dd class="text-left sm:text-right font-semibold text-ink-gray-9" data-testid="review-network">
                  {{ catalog.network?.display_name || __('No Network resolved') }}
                </dd>
              </div>
              <div class="flex flex-col sm:flex-row sm:items-start justify-between gap-1.5 sm:gap-4 p-3.5 sm:p-4">
                <dt class="text-ink-gray-6 font-medium flex items-center justify-between sm:justify-start">
                  <span>{{ __('Facilities') }}</span>
                  <button
                    type="button"
                    class="ml-2 text-xs font-semibold text-[#bc1823] underline underline-offset-4 hover:text-[#a3141d]"
                    @click="stage = 'facilities'"
                  >
                    {{ __('Edit') }}
                  </button>
                </dt>
                <dd class="text-left sm:text-right font-semibold text-ink-gray-9">
                  <span
                    v-for="facility in chosenFacilities"
                    :key="facility.facility_id"
                    class="block"
                    >{{ facility.facility_name || facility.mfl_code }}</span
                  >
                </dd>
              </div>
              <div class="flex flex-col sm:flex-row sm:items-start justify-between gap-1.5 sm:gap-4 p-3.5 sm:p-4">
                <dt class="text-ink-gray-6 font-medium flex items-center justify-between sm:justify-start">
                  <span>{{ __('Package') }}</span>
                  <button
                    type="button"
                    class="ml-2 text-xs font-semibold text-[#bc1823] underline underline-offset-4 hover:text-[#a3141d]"
                    @click="stage = 'pricing'"
                  >
                    {{ __('Edit') }}
                  </button>
                </dt>
                <dd class="text-left sm:text-right font-semibold text-ink-gray-9">
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
              <div v-if="termsAccepted" class="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5 sm:gap-4 p-3.5 sm:p-4">
                <dt class="text-ink-gray-6 font-medium">
                  {{ __('Customer Experience email') }}
                </dt>
                <dd class="text-left sm:text-right font-semibold text-ink-gray-9 break-all" data-testid="verified-account-email">
                  {{ accountEmail }}
                </dd>
              </div>
              <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5 sm:gap-4 p-3.5 sm:p-4">
                <dt class="text-ink-gray-6 font-medium">{{ __('Terms') }}</dt>
                <dd class="text-left sm:text-right font-semibold text-ink-gray-9">
                  {{ termsSnapshot?.document }}
                </dd>
              </div>
            </dl>

            <div
              v-if="!catalog.network?.name"
              class="mt-5 rounded-xl border border-amber-200 bg-amber-50/90 p-4 text-xs sm:text-sm leading-5 sm:leading-6 text-amber-900"
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
              class="mt-6 rounded-xl border border-outline-gray-2 bg-surface-gray-1/60 p-4 sm:p-5"
              aria-labelledby="review-terms-title"
              data-testid="self-onboarding-terms"
            >
              <div class="flex flex-wrap items-center justify-between gap-2.5 sm:gap-3">
                <h2 id="review-terms-title" class="text-xs sm:text-sm font-semibold text-ink-gray-9">
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
              <label class="mt-4 flex items-start gap-3 text-xs sm:text-sm leading-5 sm:leading-6 text-ink-gray-8 cursor-pointer">
                <input
                  v-model="termsAccepted"
                  required
                  :disabled="!termsSnapshot?.content_hash"
                  type="checkbox"
                  class="mt-0.5 sm:mt-1 size-5 rounded border-outline-gray-2 text-[#bc1823] accent-[#bc1823] focus:ring-[#bc1823]/20"
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
              class="mt-5 sm:mt-6 space-y-2.5 rounded-xl border border-outline-gray-2 bg-white p-4 sm:p-5 text-xs sm:text-sm"
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
              <div class="flex justify-between gap-4 border-t border-outline-gray-2/70 pt-3 text-sm sm:text-base">
                <dt class="font-semibold text-ink-gray-9">{{ __('Total incl. VAT') }}</dt>
                <dd class="font-semibold text-ink-gray-9 text-base sm:text-lg">
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
          class="rounded-2xl border border-outline-gray-2 bg-white/95 p-6 sm:p-12 text-center shadow-sm backdrop-blur"
        >
          <div
            class="mx-auto flex size-14 sm:size-16 items-center justify-center rounded-xl sm:rounded-2xl bg-emerald-100 text-2xl sm:text-3xl font-bold text-emerald-700 ring-4 sm:ring-8 ring-emerald-50 mb-4 sm:mb-6"
          >
            ✓
          </div>
          <h2 class="text-xl sm:text-3xl font-semibold text-ink-gray-9 tracking-tight">
            {{ __('Your onboarding has started') }}
          </h2>
          <p class="mx-auto mt-2.5 sm:mt-3 max-w-xl text-xs sm:text-sm leading-5 sm:leading-6 text-ink-gray-6">
            {{
              portalStatus === 'linked' || existingIdentityDetected
                ? __(
                    'An enrollment already exists for this verified identity. Your selected facilities have been added to your existing Customer Experience account. Sign in with your existing credentials to view them.',
                  )
                : __(
                    'We created your customer account and linked the selected facilities to the Network. Check this email for password setup instructions, then sign in to your portal to view your facilities.',
                  )
            }}
          </p>
          <div
            v-if="portalStatus === 'linked' || existingIdentityDetected"
            class="mx-auto mt-4 max-w-lg rounded-xl border border-blue-200 bg-blue-50/90 p-3 sm:p-3.5 text-xs text-blue-900 text-left flex items-start gap-2.5 shadow-xs"
            data-testid="linked-identity-note"
          >
            <span class="text-blue-600 font-bold shrink-0 text-sm sm:text-base leading-none">ℹ</span>
            <div class="leading-normal">
              <span class="font-semibold">{{ __('Existing Identity Linked') }}:</span>
              {{ __('Your facilities were linked to your existing Customer Experience account. Duplicate identity creation was skipped.') }}
            </div>
          </div>
          <p
            v-if="accountEmail"
            class="mx-auto mt-3.5 sm:mt-4 inline-flex items-center gap-2 rounded-full bg-surface-gray-2 border border-outline-gray-2 px-3.5 sm:px-4 py-1 sm:py-1.5 text-xs font-semibold text-ink-gray-8 max-w-full truncate"
            data-testid="success-account-email"
          >
            <span class="text-ink-gray-4">✉</span>
            <span class="truncate">{{ __('Customer Experience login: {0}', [accountEmail]) }}</span>
          </p>
          <div class="mx-auto mt-6 sm:mt-8 max-w-lg space-y-2.5 text-left">
            <div
              v-for="item in submissions"
              :key="item.mfl_code"
              class="flex items-center justify-between gap-3 rounded-xl border border-outline-gray-2 bg-surface-gray-1/70 px-3.5 sm:px-4 py-2.5 sm:py-3 text-xs sm:text-sm shadow-sm"
            >
              <span class="font-semibold text-ink-gray-9 truncate">{{ item.facility }}</span>
              <span class="rounded bg-white px-2 py-0.5 font-mono text-[11px] sm:text-xs font-semibold text-ink-gray-7 border border-outline-gray-2 shrink-0">
                {{ item.mfl_code }}
              </span>
            </div>
          </div>
          <a
            href="/login?redirect-to=/cx-portal"
            class="mt-8 sm:mt-9 inline-flex min-h-12 w-full sm:w-auto items-center justify-center gap-2 rounded-xl bg-[#bc1823] px-8 text-sm font-semibold text-white shadow-sm transition-all hover:bg-[#a3141d]"
          >
            <span>{{ portalStatus === 'linked' || existingIdentityDetected ? __('Sign in to Customer Experience') : __('Go to sign in') }}</span>
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
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { call, Dialog } from 'frappe-ui'
import OtpCodeInput from '@/components/FacilityOnboarding/OtpCodeInput.vue'
import TokenCalculator from '@/components/TokenCalculator.vue'
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
const activePricingFacilityId = ref('')
const calculatorDialogOpen = ref(false)
const landingPreselectedPackageCode = ref('')
const accountEmail = ref('')
const termsAccepted = ref(false)
const termsSnapshot = ref(null)
const termsBusy = ref(false)
const termsDialogOpen = ref(false)
const submissions = ref([])
const portalStatus = ref('')
const existingIdentityDetected = ref(false)
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
const activePricingFacility = computed(() => {
  if (!chosenFacilities.value.length) return null
  return (
    chosenFacilities.value.find(
      (item) => item.facility_id === activePricingFacilityId.value,
    ) || chosenFacilities.value[0]
  )
})

watch(
  chosenFacilities,
  (newChosen) => {
    if (
      newChosen.length &&
      (!activePricingFacilityId.value ||
        !newChosen.some((item) => item.facility_id === activePricingFacilityId.value))
    ) {
      activePricingFacilityId.value = newChosen[0].facility_id
    }
  },
  { immediate: true },
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
function isPackageSelected(code) {
  if (!activePricingFacility.value) return false
  return packageSelections.value[activePricingFacility.value.facility_id] === code
}
function selectPackageForActiveFacility(code) {
  if (activePricingFacility.value) {
    packageSelections.value[activePricingFacility.value.facility_id] = code
  }
}
function applyCurrentPackageToAll() {
  if (!activePricingFacility.value) return
  const currentCode = packageSelections.value[activePricingFacility.value.facility_id]
  if (!currentCode) return
  chosenFacilities.value.forEach((facility) => {
    packageSelections.value[facility.facility_id] = currentCode
  })
}
function onCalculatorSelectPackage(code) {
  selectPackageForActiveFacility(code)
}
function onCalculatorApplyPlan(pkg) {
  if (pkg?.item_code) {
    selectPackageForActiveFacility(pkg.item_code)
  }
  calculatorDialogOpen.value = false
}
function packageMetadata(pkg) {
  if (!pkg) {
    return {
      features: [],
      audience: '',
      badge: '',
      badgeClass: '',
      bonusLabel: '',
      bonusClass: '',
      capacityLabel: '',
      isPopular: false,
    }
  }
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
  const code = (pkg.item_code || '').toUpperCase()
  const name = (pkg.display_name || '').toUpperCase()
  const tokens = Number(pkg.token_quantity || 0)

  const isGrowth = code.includes('GROWTH') || name.includes('GROWTH') || tokens === 2800
  const isScale = code.includes('SCALE') || name.includes('SCALE') || tokens === 6250
  const isStarter = code.includes('STARTER') || name.includes('STARTER') || tokens === 1000

  let badge = ''
  let badgeClass = 'bg-surface-gray-2 text-ink-gray-7 border border-outline-gray-2'
  let isPopular = false

  if (isFree) {
    badge = __('Free Trial')
    badgeClass = 'bg-surface-gray-2 text-ink-gray-7 border border-outline-gray-2'
  } else if (isGrowth) {
    badge = __('Popular • +12%')
    badgeClass = 'bg-[#bc1823] text-white shadow-xs'
    isPopular = true
  } else if (isScale) {
    badge = __('Best Value • +25%')
    badgeClass = 'bg-[#fdf2f3] text-[#bc1823] border border-[#f0d6d8]'
  } else if (isStarter) {
    badge = __('Entry Tier')
    badgeClass = 'bg-surface-gray-2 text-ink-gray-7 border border-outline-gray-2'
  } else if (metrics.badge) {
    badge = metrics.badge
  }

  let bonusLabel = ''
  let bonusClass = 'bg-surface-gray-2 text-ink-gray-6 border-outline-gray-2'
  if (isFree) {
    bonusLabel = __('100% Free')
    bonusClass = 'bg-surface-gray-2 text-ink-gray-7 border-outline-gray-2'
  } else if (isGrowth) {
    bonusLabel = __('+12% Bonus')
    bonusClass = 'bg-emerald-50 text-emerald-700 border-emerald-200/60'
  } else if (isScale) {
    bonusLabel = __('+25% Bonus')
    bonusClass = 'bg-[#fdf2f3] text-[#bc1823] border-[#f0d6d8]'
  } else if (isStarter) {
    bonusLabel = __('Base Rate')
    bonusClass = 'bg-surface-gray-2 text-ink-gray-6 border-outline-gray-2'
  }

  let capacityLabel = ''
  if (isFree) capacityLabel = __('~10 complete patient journeys')
  else if (isStarter) capacityLabel = __('~25 complete patient journeys')
  else if (isGrowth) capacityLabel = __('~70 complete patient journeys')
  else if (isScale) capacityLabel = __('~155 complete patient journeys')
  else if (tokens) capacityLabel = `~${Math.round(tokens / 40)} ${__('patient journeys')}`

  let audience = ''
  if (isFree) audience = __('For trialing clinics & new facilities')
  else if (isStarter) audience = __('For solo practices & small outpatient clinics')
  else if (isGrowth) audience = __('For active clinics with labs & diagnostics')
  else if (isScale) audience = __('For high-volume centers & full hospitals')
  else audience = metrics.audience || __('For healthcare facilities & active clinics')

  let features = []
  if (isFree) {
    features = [
      __('10 full clinical patient journeys'),
      __('Digital Registry & HFR lookup included'),
      __('Zero customer financial liability'),
    ]
  } else if (isStarter) {
    features = [
      __('Outpatient consultations & vitals'),
      __('Prescriptions & laboratory orders'),
      __('KES 6.00 per token base rate'),
    ]
  } else if (isGrowth) {
    features = [
      __('Multi-department workflows & pharmacy'),
      __('Diagnostic imaging & laboratory tests'),
      __('KES 5.36 per token effective rate (+12%)'),
    ]
  } else if (isScale) {
    features = [
      __('Inpatient admissions & surgical wards'),
      __('Comprehensive claims & priority support'),
      __('KES 4.80 per token effective rate (+25%)'),
    ]
  } else if (Array.isArray(metrics.features) && metrics.features.length) {
    features = metrics.features.slice(0, 3)
  } else {
    features = [
      pkg.coverage_summary || __('Standard clinical operations'),
      __('Flexible token balance top-ups'),
      __('Customer Experience Portal access'),
    ]
  }

  return {
    audience,
    badge,
    badgeClass,
    bonusLabel,
    bonusClass,
    capacityLabel,
    features,
    isPopular,
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

function money(value, currency = 'KES') {
  const num = Number(value || 0)
  const curr = currency || 'KES'
  return `${curr} ${num.toLocaleString('en-KE', { maximumFractionDigits: 0 })}`
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
function startWithSelectedPlan(pkg) {
  if (pkg?.item_code) {
    landingPreselectedPackageCode.value = pkg.item_code
  }
  stage.value = 'identity'
  if (typeof window !== 'undefined') {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
}
function goBack() {
  const previous = previousStage(stage.value)
  if (previous) stage.value = previous
}
function continueFacilities() {
  if (selectedFacilities.value.length) {
    const existing = packageSelections.value
    packageSelections.value = Object.fromEntries(
      selectedFacilities.value.map((facilityId) => {
        const previousCode = existing[facilityId] || landingPreselectedPackageCode.value
        return [facilityId, previousCode || '']
      }),
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
        const previousCode = previousSelections[facilityId] || landingPreselectedPackageCode.value
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
    if (data.is_existing_identity || data.portal_status === 'linked') {
      existingIdentityDetected.value = true
    }
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
  existingIdentityDetected.value = false
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
