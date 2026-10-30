<template>
  <div class="vx">
    <header class="site">
      <div class="wrap">
        <a class="lockup" href="/" :aria-label="__('Tiberbu CareverseHIMS Value Express')">
          <TiberbuWordmark class="wm" />
          <span class="prod">CareverseHIMS<b>Value Express</b></span>
        </a>
        <span class="help">
          <a href="/#contact">{{ __('Need help?') }}</a>
          <a href="/login?redirect-to=/cx-portal">{{ __('Sign in') }}</a>
        </span>
      </div>
    </header>

    <main>
      <div class="wrap" :class="{ wide: stage === 'pricing' }">
        <div class="intro">
          <span class="badge" style="align-self: flex-start"><i></i>{{ __('CareverseHIMS Value Express') }}</span>
          <p>{{ networkName ? __('Set up {0} with {1} in four simple steps.', [facilityName || __('your facility'), networkName]) : __('Set up your facility in four simple steps.') }}</p>
        </div>
        <ol v-if="stage !== 'success'" class="stepper" :aria-label="__('Onboarding steps')">
          <li
            v-for="(item, index) in progressSteps"
            :key="item.key"
            :data-s="item.status === 'complete' ? 'done' : item.status === 'current' ? 'current' : 'todo'"
            :aria-current="item.status === 'current' ? 'step' : undefined"
          >
            <span class="dot">{{ item.status === 'complete' ? '✓' : index + 1 }}</span>
            <span>
              <b>{{ item.label }}<span class="sr-only"> — {{ item.statusLabel }}</span></b>
              <small>{{ item.subtitle }}</small>
            </span>
          </li>
        </ol>
        <div v-if="errorMessage" class="alert" role="alert">
          <span>{{ errorMessage }}</span>
          <span style="display: flex; gap: 14px">
            <a v-if="registrationConflictDetected" href="/login?redirect-to=/cx-portal" data-testid="duplicate-signin">{{ __('Sign in to Tiberbu Express') }}</a>
            <a v-if="registrationConflictDetected && supportEmail" :href="`mailto:${supportEmail}`" data-testid="duplicate-support">{{ __('Contact support') }}</a>
            <button v-if="sessionExpired" type="button" class="btn link" @click="reset">{{ __('Start again') }}</button>
          </span>
        </div>
      </div>

      <!-- STEP 1: verify -->
      <section v-if="stage === 'identity' || stage === 'otp'" class="wrap">
        <form v-if="stage === 'identity'" class="card" @submit.prevent="startIdentity">
          <div class="card-h">
            <h1>{{ __('Let’s find your facility') }}</h1>
            <div class="tip">
              <button type="button" :aria-expanded="tipOpen" aria-controls="tip-pop" @click="tipOpen = !tipOpen">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 7.5v.5" /></svg>
                {{ __('How this works') }}
              </button>
              <div v-if="tipOpen" id="tip-pop" class="pop">
                <b>{{ __('How this works') }}</b>
                <ol>
                  <li><span>1</span><div><b>{{ __('Enter your ID') }}</b>{{ __('Provide an identification number linked to your facility record.') }}</div></li>
                  <li><span>2</span><div><b>{{ __('Verify with OTP') }}</b>{{ __('We’ll send a one-time verification code to the registered contact.') }}</div></li>
                  <li><span>3</span><div><b>{{ __('Find your facility') }}</b>{{ __('After verification, we’ll show the facilities associated with your details.') }}</div></li>
                </ol>
              </div>
            </div>
          </div>
          <p class="muted" style="margin-top: 12px">{{ __('Enter the owner’s or administrator’s ID. We’ll send a code to the contact on the facility record.') }}</p>
          <div class="form">
            <div class="row2">
              <div class="field">
                <label for="id-type">{{ __('Identification type') }}</label>
                <select id="id-type" v-model="identityType">
                  <option value="national_id">{{ __('National ID') }}</option>
                  <option value="passport">{{ __('Passport') }}</option>
                  <option value="foreigner_id">{{ __('Foreigner ID') }}</option>
                  <option value="alien_id">{{ __('Alien ID') }}</option>
                </select>
              </div>
              <div class="field">
                <label for="id-number">{{ __('Identification number') }}</label>
                <input id="id-number" v-model.trim="identityNumber" required autocomplete="off" :placeholder="__('Enter your ID number')" />
                <span class="hint">{{ __('Use the identification number linked to your facility record.') }}</span>
              </div>
            </div>
            <button class="btn primary" :disabled="busy" style="justify-self: start">
              {{ busy ? __('Checking your details…') : __('Verify & Find My Facility') }}
            </button>
          </div>
        </form>

        <form v-else class="card" @submit.prevent="verifyOtp">
          <div v-if="hfrRetryPending" class="status-note" role="status" style="margin-top: 0">
            <p>
              {{
                hfrRetryExhausted
                  ? __('We could not load facility details. Please contact support for help continuing.')
                  : __('Your contact is verified, but facility details are temporarily unavailable. Retry to continue without requesting another code.')
              }}
            </p>
            <button v-if="!hfrRetryExhausted" type="button" class="btn ghost small" :disabled="busy" @click="retryHfr">
              {{ busy ? __('Checking facilities…') : __('Retry facility lookup') }}
            </button>
          </div>
          <template v-else>
            <h1>{{ __('Enter your verification code') }}</h1>
            <p v-if="deliveryStatus === 'unavailable'" class="status-note" role="status">
              {{ __('We could not deliver a code just now. Retry delivery to this verified contact session.') }}
            </p>
            <p v-else class="muted" style="margin-top: 10px" role="status">
              {{
                delivery.masked_destination && delivery.reused
                  ? __('We already sent a 6-digit code by {0} to {1}. Enter that code; no new code was sent.', [deliveryChannelLabel, delivery.masked_destination])
                  : delivery.masked_destination
                    ? __('We sent a 6-digit code by {0} to {1}.', [deliveryChannelLabel, delivery.masked_destination])
                    : __('If we can verify your details, a 6-digit code will be sent to your registered contact.')
              }}
              {{ __('The code expires in {0} minutes.', [expiryMinutes]) }}
            </p>
            <div class="form">
              <div class="field">
                <OtpCodeInput v-model="otp" :disabled="busy" :error="otpError" :label="__('Verification code')" />
              </div>
              <div style="display: flex; gap: 16px; flex-wrap: wrap; align-items: center">
                <button class="btn primary" :disabled="busy || otp.length !== 6">{{ busy ? __('Verifying…') : __('Verify code') }}</button>
                <button type="button" class="btn link" :disabled="busy" @click="editIdentity">{{ __('Use a different ID') }}</button>
                <span class="muted" style="font-size: 0.9rem" aria-live="polite">
                  <button v-if="canResendOtp(delivery, resendIn, busy)" type="button" class="btn link" @click="resendOtp">
                    {{ deliveryStatus === 'unavailable' ? __('Retry code delivery') : __('Resend code') }}
                  </button>
                  <template v-else-if="resendIn > 0">{{ __('Resend code in {0}', [formatCountdown(resendIn)]) }}</template>
                </span>
              </div>
            </div>
          </template>
        </form>

        <div class="assist">
          <b>{{ __('No longer have access to this contact? Having trouble finding your facility?') }}</b>
          <span class="muted">{{ __('Our Value Express onboarding team can help verify your facility information and guide you through onboarding.') }}</span>
          <a href="/#contact">{{ __('Get onboarding assistance →') }}</a>
        </div>
      </section>

      <!-- STEP 2: facility -->
      <section v-else-if="stage === 'facilities'" class="wrap">
        <form class="card" @submit.prevent="continueFacilities">
          <h1>{{ __('Select the facility you want to onboard') }}</h1>
          <p class="muted" style="margin-top: 10px">
            {{ __('We found the facilities linked to your verified details. Select one or more eligible facilities. You can choose a different Value Express plan for each facility.') }}
          </p>
          <p v-if="identityPreview.full_name || identityPreview.email" class="verified" :aria-label="__('Verified identity')">
            ✓ {{ __('Verified') }}: <b>{{ identityPreview.full_name }}</b>
            <span v-if="identityPreview.email"> · {{ identityPreview.email }}</span>
            <span v-if="identityPreview.phone"> · {{ identityPreview.phone }}</span>
          </p>
          <p v-if="!facilities.length" class="catalog-note" role="status">
            {{ __('We couldn’t find eligible facilities linked to your details. Check that you used the right identification, or contact us and we’ll help.') }}
          </p>
          <div v-if="facilities.length > FACILITY_PAGE_SIZE" class="fsearch field">
            <input v-model="facilitySearch" type="search" autocomplete="off" data-testid="facility-search" :aria-label="__('Search facilities')" :placeholder="__('Search by facility name, Facility ID or MFL code')" />
            <span class="muted" data-testid="facility-selected-count" aria-live="polite">{{ __('{0} of {1} selected', [selectedFacilities.length, facilities.length]) }}</span>
          </div>
          <p v-if="facilities.length && !facilityPageView.total" class="catalog-note" role="status">{{ __('No facilities match “{0}”.', [facilitySearch.trim()]) }}</p>
          <div class="flist">
            <component
              :is="selectable(facility) ? 'label' : 'div'"
              v-for="facility in facilityPageView.items"
              :key="facility.facility_id"
              class="fac"
              :class="{ off: !selectable(facility) }"
              :aria-disabled="selectable(facility) ? undefined : 'true'"
            >
              <input
                v-if="selectable(facility)"
                v-model="selectedFacilities"
                type="checkbox"
                :value="facility.facility_id"
                :aria-label="__('Select {0}', [facility.facility_name || facility.mfl_code])"
                data-testid="facility-select-checkbox"
              />
              <svg v-else class="lock" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V7a4 4 0 018 0v4" /></svg>
              <div>
                <h3>{{ facility.facility_name || facility.mfl_code }}</h3>
                <div class="meta">
                  <span v-if="facilityId(facility)" data-testid="onboarding-facility-id">{{ __('Facility ID') }} <b>{{ facilityId(facility) }}</b></span>
                  <span>MFL <b>{{ facility.mfl_code }}</b></span>
                  <span>{{ facility.facility_level || __('Level not on record') }}</span>
                  <span v-if="facility.facility_type">{{ facility.facility_type }}</span>
                </div>
                <p v-if="facility.onboarding_blocked" class="why" data-testid="facility-already-onboarded">
                  {{ __('This facility is already set up and can’t be added to a new request here.') }}
                  <a href="/login?redirect-to=/cx-portal">{{ __('Sign in to Tiberbu Express →') }}</a>
                </p>
                <p v-else-if="facility.onboarding_eligible !== true" class="why">
                  {{
                    facility.facility_eligibility_reason === 'missing_level'
                      ? __('We couldn’t confirm this facility’s level in the registry, so it can’t be onboarded online. Our team can check it with you.')
                      : __('Value Express is for Level 2 and Level 3 outpatient facilities, so this one can’t be selected.')
                  }}
                  <a href="/#fit">{{ __('Enquire about CareverseHIMS Advanced & Enterprise →') }}</a>
                </p>
              </div>
              <span class="chip" :class="selectable(facility) ? 'ok' : 'no'">
                {{ facility.onboarding_blocked ? __('Already onboarded') : selectable(facility) ? __('Eligible') : __('Not eligible') }}
              </span>
            </component>
          </div>
          <nav v-if="facilityPageView.pages > 1" class="pager" :aria-label="__('Facility pages')" data-testid="facility-pager">
            <button type="button" class="btn ghost small" :disabled="facilityPageView.page <= 1" @click="facilityPageNumber = facilityPageView.page - 1">← {{ __('Previous') }}</button>
            <span class="muted" data-testid="facility-pager-status">{{ __('Showing {0}–{1} of {2}', [facilityPageView.from, facilityPageView.to, facilityPageView.total]) }}</span>
            <button type="button" class="btn ghost small" :disabled="facilityPageView.page >= facilityPageView.pages" @click="facilityPageNumber = facilityPageView.page + 1">{{ __('Next') }} →</button>
          </nav>
          <div class="assist"><b>{{ __('Can’t see your facility?') }}</b><a href="/#contact">{{ __('Get onboarding assistance →') }}</a></div>
          <div class="actions">
            <button type="button" class="btn ghost" @click="reset">{{ __('Start over') }}</button>
            <div class="next">
              <button class="btn primary" :disabled="!selectedFacilities.length">
                {{ __('Continue to Packages →') }}
                <span v-if="selectedFacilities.length" class="sr-only" data-testid="facility-continue-count">{{ selectedFacilities.length }}</span>
              </button>
              <small>{{ selectedFacilities.length ? __('Next, you’ll choose Value Express Flex or Fixed for each selected facility.') : __('Select at least one eligible facility to continue.') }}</small>
            </div>
          </div>
        </form>
      </section>

      <!-- STEP 3: package -->
      <form v-else-if="stage === 'pricing'" @submit.prevent="continuePricing">
        <section class="wrap wide">
          <div class="card">
            <h1>{{ __('Choose how you want to use CareverseHIMS') }}</h1>
            <p class="muted" style="margin-top: 10px">
              {{
                hasFixed
                  ? __('Select the Value Express plan that best fits each facility’s expected activity. Flex packages are prepaid, and purchased tokens remain available while your account is active. Fixed is a set monthly fee.')
                  : __('Select the Value Express Flex package that best fits each facility’s expected activity. Packages are prepaid, and purchased tokens remain available while your account is active.')
              }}
            </p>
            <div ref="couponPanelRef" class="couponline coupon">
              <button ref="couponToggleRef" type="button" class="btn link" data-testid="partner-coupon-toggle" :aria-expanded="couponOpen" aria-controls="partner-coupon-panel" @click="couponOpen ? closeCoupon() : openCoupon()">
                {{ partnerId ? `${__('Partner Coupon')}: ${partnerId}` : __('Have a Partner Coupon?') }}
              </button>
              <div v-if="couponOpen" id="partner-coupon-panel" class="pop" role="dialog" :aria-label="__('Enter Partner Coupon')">
                <div class="field">
                  <label for="partner-coupon-input">{{ __('Partner Coupon (6 digits)') }}</label>
                  <input id="partner-coupon-input" ref="couponInputRef" :value="partnerId" inputmode="numeric" autocomplete="off" maxlength="6" pattern="[0-9]{6}" placeholder="123456" :aria-invalid="Boolean(partnerId && partnerId.length !== 6)" @input="onPartnerIdInput" @keydown.enter.prevent="closeCoupon" />
                  <span class="hint">{{ partnerId && partnerId.length !== 6 ? __('Enter all six digits, or clear the field to leave it blank.') : __('Leave it blank if you don’t have one.') }}</span>
                </div>
                <p v-if="couponApplied" class="ok" data-testid="partner-coupon-applied">✓ {{ __('Partner Coupon applied') }}<template v-if="catalog.network?.display_name"> · <span data-testid="partner-coupon-network">{{ catalog.network.display_name }}</span></template>: +{{ couponTokens.toLocaleString() }} {{ __('bonus tokens per facility with your first purchase') }}</p>
                <div style="display: flex; gap: 10px; margin-top: 10px">
                  <button type="button" class="btn primary small" @click="closeCoupon">{{ __('Done') }}</button>
                  <button type="button" class="btn ghost small" data-testid="partner-coupon-close" @click="closeCoupon">{{ __('Close') }}</button>
                </div>
              </div>
            </div>

            <p v-if="catalogBusy" class="catalog-note" role="status" aria-live="polite" data-testid="catalog-loading">{{ __('Loading packages and current pricing…') }}</p>
            <div v-else-if="catalogError" class="catalog-note" role="alert" data-testid="catalog-error">
              <p>{{ catalogError }}</p>
              <button type="button" class="btn link" @click="loadCatalog(true)">{{ __('Try loading packages again') }} →</button>
            </div>
            <p v-else-if="partnerId && partnerId.length !== 6" class="catalog-note" role="status" data-testid="catalog-partner-incomplete">{{ __('Enter all six digits of your Partner Coupon, or clear it to continue without one.') }}</p>
            <div v-else-if="!catalog.packages?.length" class="catalog-note" role="status" data-testid="catalog-empty">
              <p>{{ __('There are no packages available right now. Please try again later or contact us.') }}</p>
              <button type="button" class="btn link" @click="loadCatalog(true)">{{ __('Try loading packages again') }} →</button>
            </div>

            <template v-else-if="activePricingFacility">
              <p v-if="carried" class="prefnote" data-testid="carried-choice">{{ __('Preselected from your choice on the Value Express page: {0}. You can change it below.', [carriedLabel]) }}</p>
              <div v-if="chosenFacilities.length > 1" class="factabs" role="tablist" :aria-label="__('Selected facilities')">
                <button
                  v-for="facility in chosenFacilities"
                  :key="facility.facility_id"
                  type="button"
                  role="tab"
                  :aria-selected="facility.facility_id === activePricingFacility.facility_id"
                  @click="activePricingFacilityId = facility.facility_id"
                >
                  {{ facility.facility_name || facility.mfl_code }}
                  <small><span v-if="isReady(facility.facility_id)" class="ok">✓ </span>{{ choiceLabel(facility.facility_id) }}</small>
                </button>
              </div>
              <div v-if="hasFixed" class="planpick">
                <button type="button" :aria-pressed="activePlan === 'flex'" data-testid="plan-flex" @click="setPlan('flex')">
                  <b>{{ __('Value Express Flex') }}</b>
                  <span>{{ __('Pay as you use with prepaid tokens. From {0}.', [money(entryPrice, currency)]) }}</span>
                </button>
                <button type="button" :aria-pressed="activePlan === 'fixed'" :disabled="!activeFixed" data-testid="plan-fixed" @click="setPlan('fixed')">
                  <b>{{ __('Value Express Fixed') }}</b>
                  <span>
                    {{
                      activeFixed
                        ? __('One predictable fixed fee. {0} {1} for your {2} facility.', [money(activeFixed.price_ex_vat, activeFixed.currency), __(periodLabel(activeFixed.billing_period)), activePricingFacility.facility_level])
                        : __('Not offered for this facility’s level.')
                    }}
                  </span>
                </button>
              </div>
              <div class="calcline">
                <span>{{ __('Not sure which plan or how many tokens you need?') }}</span>
                <a href="/#calculator" target="_blank" rel="noopener">{{ __('Calculate My Token Requirement →') }}</a>
              </div>

              <div v-if="activePlan === 'flex'" :data-testid="`facility-package-${activePricingFacility.facility_id}`">
                <h2 style="margin-top: 28px">{{ __('Value Express Flex - Pay As You Use') }}</h2>
                <p class="muted" style="margin-top: 6px">{{ __('Each package provides prepaid Careverse Tokens. The packages differ in the number of tokens you buy and the value you get. The CareverseHIMS product is the same.') }}</p>
                <div v-if="accessTokens" class="access">
                  <span class="n">−{{ accessTokens.toLocaleString() }}</span>
                  <p><b>{{ __('{0} tokens a month for system access.', [accessTokens.toLocaleString()]) }}</b> {{ __('This is deducted from your balance at the start of each funded month, before service-point and patient-bill tokens. Each card shows what is left for services in your first month.') }}</p>
                </div>
                <div class="pkgs" data-testid="package-grid" :style="{ '--cols': gridColumns((catalog.packages?.length || 0) + (customOffer ? 1 : 0)) }">
                  <div v-for="pkg in catalog.packages" :key="pkg.item_code" class="pkg" :class="{ sel: flexChoice[activeId] === pkg.item_code }">
                    <span v-if="recommendedKey === pkg.item_code" class="rec">{{ carried?.package === pkg.item_code ? __('Popular choice for you') : __('Popular') }}</span>
                    <span class="nm">{{ pkg.display_name || pkg.item_code }}</span>
                    <span class="bf">{{ pkg.description }}</span>
                    <span class="pr">{{ money(priceOf(pkg), pkg.currency) }}</span>
                    <span class="vat">{{ __('excluding {0}', [pkg.vat_label || 'VAT']) }}</span>
                    <dl>
                      <dt>{{ __('Tokens') }}</dt><dd>{{ Number(pkg.token_quantity || 0).toLocaleString() }}</dd>
                      <dt>{{ __('Suits') }}</dt><dd>{{ pkg.audience || '—' }}</dd>
                      <dt>{{ __('Price per token') }}</dt><dd>{{ currencyOf(pkg) }} {{ perTokenRate(pkg).toFixed(2) }}</dd>
                    </dl>
                    <span v-if="morePercent(pkg, catalog.packages)" class="more">{{ __('Includes {0}% more tokens', [morePercent(pkg, catalog.packages)]) }}</span>
                    <span v-if="bonusLine" class="bonus" data-testid="package-bonus">{{ bonusLine }}</span>
                    <span v-if="accessTokens" class="firstmo">
                      {{ __('For services in month 1:') }} <b class="mono">{{ monthOneTokens(pkg.token_quantity, welcomeBonusTokens, accessTokens).toLocaleString() }}</b> {{ __('tokens') }}
                    </span>
                    <button type="button" class="btn" :class="flexChoice[activeId] === pkg.item_code ? 'primary' : 'ghost'" :aria-pressed="flexChoice[activeId] === pkg.item_code" @click="chooseFlex(pkg.item_code)">
                      {{ flexChoice[activeId] === pkg.item_code ? __('✓ Selected') : __('Select {0}', [pkg.display_name || pkg.item_code]) }}
                    </button>
                  </div>
                  <div v-if="customOffer" class="pkg" :class="{ sel: flexChoice[activeId] === CUSTOM }" data-testid="custom-package">
                    <span v-if="recommendedKey === CUSTOM" class="rec">{{ __('Popular choice for you') }}</span>
                    <span class="nm">{{ customOffer.display_name || __('Custom') }}</span>
                    <span class="bf">{{ __('Set your own amount. Tokens are worked out at the rate of the package your amount reaches.') }}</span>
                    <label class="lbl" for="custom-amount" style="margin-top: 6px">{{ __('Your amount ({0})', [customOffer.currency]) }}</label>
                    <input id="custom-amount" class="cuin" type="number" :min="customOffer.min_amount" step="500" inputmode="numeric" :value="customAmountFor(activeId)" :aria-invalid="!activeCustomQuote.ok" aria-describedby="custom-amount-help" @input="setCustomAmount($event.target.value)" />
                    <span id="custom-amount-help" :class="activeCustomQuote.ok ? 'vat' : 'cuerr'">{{ activeCustomQuote.ok ? __('excluding VAT · minimum {0}', [money(customOffer.min_amount, customOffer.currency)]) : __('Minimum {0} ({1} tokens).', [money(customOffer.min_amount, customOffer.currency), Number(customOffer.min_tokens).toLocaleString()]) }}</span>
                    <dl>
                      <dt>{{ __('Tokens') }}</dt><dd>{{ activeCustomQuote.ok ? activeCustomQuote.tokens.toLocaleString() : '—' }}</dd>
                      <dt>{{ __('Suits') }}</dt><dd>{{ __('Any size — set your own amount') }}</dd>
                      <dt>{{ __('Price per token') }}</dt><dd>{{ customOffer.currency }} {{ activeCustomQuote.rate.toFixed(2) }}</dd>
                      <dt>{{ __('You pay') }}</dt><dd>{{ activeCustomQuote.ok ? money(activeCustomQuote.charge, customOffer.currency, 2) : '—' }}</dd>
                    </dl>
                    <span class="more">{{ __('{0} rate · no first-purchase bonus', [activeCustomQuote.tier]) }}</span>
                    <span v-if="accessTokens && activeCustomQuote.ok" class="firstmo">
                      {{ __('For services in month 1:') }} <b class="mono">{{ monthOneTokens(activeCustomQuote.tokens, 0, accessTokens).toLocaleString() }}</b> {{ __('tokens') }}
                    </span>
                    <button type="button" class="btn" :class="flexChoice[activeId] === CUSTOM ? 'primary' : 'ghost'" :aria-pressed="flexChoice[activeId] === CUSTOM" :disabled="!activeCustomQuote.ok" @click="chooseFlex(CUSTOM)">
                      {{ flexChoice[activeId] === CUSTOM ? __('✓ Selected') : __('Select Custom') }}
                    </button>
                  </div>
                </div>
                <p class="foot">{{ __('Token use depends on completed service-point transactions and patient-bill value. First-purchase bonus tokens apply to the listed packages, not Custom, subject to the applicable offer and terms.') }}</p>
              </div>

              <div v-else class="fixed">
                <h2 style="margin-top: 28px">{{ __('Value Express Fixed') }}</h2>
                <p class="muted" style="margin-top: 6px">{{ __('Value Express Fixed gives your facility CareverseHIMS Value Express through a straightforward monthly subscription. It suits facilities that value cost predictability and don’t want to monitor token balances or make top-ups. The fee depends on your facility’s level.') }}</p>
                <div class="tiers" :style="{ '--cols': gridColumns(catalog.fixed_packages?.length || 0, 3) }">
                  <button v-for="pkg in catalog.fixed_packages" :key="pkg.item_code" type="button" class="tier" :aria-pressed="activeFixed?.item_code === pkg.item_code" :disabled="activeFixed?.item_code !== pkg.item_code" data-testid="fixed-tier">
                    <span class="lbl">{{ pkg.facility_levels?.[0] || pkg.display_name }} {{ __('facility') }}</span>
                    <b>{{ money(pkg.price_ex_vat, pkg.currency) }}</b>
                    <span class="muted">{{ __('{0}, excluding {1}', [__(periodLabel(pkg.billing_period)), pkg.vat_label || 'VAT']) }}</span>
                    <span style="font-size: 0.85rem; color: var(--ink-2)">{{ activeFixed?.item_code === pkg.item_code ? __('Matches your facility level') : __('Not your facility’s level') }}</span>
                  </button>
                </div>
                <ul>
                  <li>{{ __('Full Value Express platform access') }}</li>
                  <li>{{ __('SHA eClaims capabilities') }}</li>
                  <li>{{ __('Guided self-onboarding and activation support') }}</li>
                  <li>{{ __('Recurring virtual CareverseHIMS training') }}</li>
                  <li>{{ __('Continuous remote support') }}</li>
                  <li>{{ __('Predictable monthly expenditure') }}</li>
                </ul>
              </div>

              <div v-if="chosenFacilities.length > 1 && isReady(activeId)" class="nextfac" data-testid="next-facility">
                <span>✓ {{ nextFacility ? __('{0} is set.', [activePricingFacility.facility_name || activePricingFacility.mfl_code]) : __('All {0} facilities are set.', [chosenFacilities.length]) }}</span>
                <button v-if="nextFacility" type="button" class="btn primary" @click="goToFacility(nextFacility.facility_id)">{{ __('Next: {0} →', [nextFacility.facility_name || nextFacility.mfl_code]) }}</button>
                <button v-else class="btn primary" :disabled="termsBusy">{{ __('Continue to Review →') }}</button>
              </div>
            </template>
          </div>
        </section>
        <div class="sumbar">
          <div class="wrap">
            <span>
              <b>{{ __('{0} of {1}', [readyCount, chosenFacilities.length]) }}</b>
              {{ chosenFacilities.length === 1 ? __('facility ready') : __('facilities ready') }}
              <template v-if="totals"> · {{ __('Total to pay') }} <b>{{ money(totals.exVat, totals.currency) }}</b> <span class="muted">{{ __('excl. VAT') }}</span></template>
            </span>
            <span style="display: flex; flex-direction: column; align-items: flex-end; gap: 4px">
              <button class="btn primary" :disabled="!allPackagesSelected || termsBusy || catalogBusy || !!catalogError || !catalogCurrent">{{ termsBusy ? __('Loading terms…') : __('Continue to Review →') }}</button>
              <small v-if="!allPackagesSelected" class="hintline">{{ chosenFacilities.length > 1 ? __('Choose a package for each facility to continue.') : __('Choose a package to continue.') }}</small>
            </span>
          </div>
        </div>
      </form>

      <!-- STEP 4: review -->
      <section v-else-if="stage === 'review'" class="wrap">
        <form class="card" @submit.prevent="submit">
          <h1>{{ __('Review and confirm') }}</h1>
          <p class="muted" style="margin-top: 10px">{{ __('Check your selections. You’ll pay the invoice in Tiberbu Express, and tokens or your subscription start once payment is confirmed. Go-live timing depends on facility verification, payment, configuration and user readiness.') }}</p>
          <div class="tbl">
            <table class="rv">
              <thead><tr><th>{{ __('Facility') }}</th><th>{{ __('Plan') }}</th><th>{{ __('Amount') }}</th></tr></thead>
              <tbody>
                <tr v-for="facility in chosenFacilities" :key="facility.facility_id">
                  <td><b>{{ facility.facility_name || facility.mfl_code }}</b><br /><span class="muted mono" style="font-size: 0.8rem">{{ facilityId(facility) || facility.mfl_code }}</span></td>
                  <td>
                    {{ reviewPlan(facility.facility_id).title }}<br />
                    <span class="muted" style="font-size: 0.85rem">{{ reviewPlan(facility.facility_id).detail }}</span><br />
                    <button type="button" class="btn link chg" :data-testid="`change-${facility.facility_id}`" @click="changeFacility(facility.facility_id)">{{ __('Change') }}</button>
                  </td>
                  <td>{{ money(priceOf(selectedPackageFor(facility.facility_id)), selectedPackageFor(facility.facility_id)?.currency, 2) }}</td>
                </tr>
              </tbody>
              <tfoot v-if="totals">
                <tr><td colspan="2">{{ __('Subtotal') }}</td><td>{{ money(totals.exVat, totals.currency, 2) }}</td></tr>
                <tr><td colspan="2">{{ totals.vatLabel }}</td><td>{{ money(totals.vat, totals.currency, 2) }}</td></tr>
                <tr><td colspan="2"><b>{{ __('Total to pay') }}</b> <span class="muted" style="font-size: 0.85rem">· {{ __('invoiced in Tiberbu Express') }}</span></td><td>{{ money(totals.gross, totals.currency, 2) }}</td></tr>
              </tfoot>
            </table>
          </div>
          <dl class="rv-meta">
            <div><dt>{{ __('Partner Coupon') }}</dt><dd data-testid="review-partner-coupon"><template v-if="catalog.network?.name && partnerId"><span class="mono">{{ partnerId }}</span> {{ catalog.network.display_name }}</template><template v-else>{{ __('Not applied') }}</template></dd></div>
            <div v-if="termsAccepted"><dt>{{ __('Tiberbu Express sign-in') }}</dt><dd data-testid="verified-account-email">{{ accountEmail || '—' }}</dd></div>
          </dl>
          <p v-if="!catalog.network?.name" class="muted" style="font-size: 0.88rem; margin-top: 8px" data-testid="no-partner-coupon-note">
            {{ __('No Partner Coupon applied. You can submit without one; if a partner referred you, your facilities can be linked to them later.') }}
            <button type="button" class="btn link" @click="stage = 'pricing'">{{ __('Add a Partner Coupon') }}</button>
          </p>
          <section class="terms" data-testid="self-onboarding-terms" aria-labelledby="review-terms-title">
            <div class="row">
              <b id="review-terms-title">{{ termsSnapshot?.document || __('Terms and Conditions') }}</b>
              <button type="button" class="btn ghost small" :disabled="!termsSnapshot?.rendered_html" data-testid="terms-download" @click="downloadTerms">{{ __('Download Terms') }}</button>
            </div>
            <label id="agree-row" class="agree" :class="{ nudge: agreeNudge }">
              <input v-model="termsAccepted" type="checkbox" :disabled="!termsSnapshot?.content_hash" data-testid="terms-acceptance" />
              <span>
                {{ __('I have read and accept the') }}
                <a href="#" aria-haspopup="dialog" @click.prevent="termsDialogOpen = true">{{ __('Value Express terms') }}</a>
                {{ __('and the') }}
                <a href="/#flex-rules" target="_blank" rel="noopener">{{ __('token rules') }}</a>.
              </span>
            </label>
            <p v-if="!accountEmail" class="status-note" role="alert">{{ __('We couldn’t find an email address on your verified profile for Tiberbu Express access. Please contact us and we’ll help you continue.') }}</p>
          </section>
          <div class="actions">
            <button type="button" class="btn ghost" :disabled="busy" @click="goBack">← {{ __('Back') }}</button>
            <div class="next">
              <button class="btn primary" :aria-disabled="busy || !reviewReady ? 'true' : undefined" aria-describedby="confirm-hint" data-testid="confirm-submit">
                {{ busy ? __('Sending your request…') : __('Confirm and get started') }}
              </button>
              <small v-if="!termsAccepted" id="confirm-hint">{{ __('Tick the box above to confirm.') }}</small>
            </div>
          </div>
        </form>
      </section>

      <!-- done -->
      <section v-else class="wrap">
        <div class="card done success">
          <div class="tick">✓</div>
          <h1>{{ __('Your request has been submitted') }}</h1>
          <p class="muted" style="margin: 10px auto 0; max-width: 56ch">
            {{
              portalStatus === 'linked' || existingIdentityDetected
                ? __('Your selected facilities are linked to your existing Tiberbu Express account. Sign in with your usual details to review your draft order and pay its invoice.')
                : catalog.network?.name
                  ? __('Your Tiberbu Express account is ready, and your selected facilities are linked to the Network. Check your email for password setup instructions, then sign in to review your draft order and pay its invoice.')
                  : __('Your Tiberbu Express account is ready. Check your email for password setup instructions, then sign in to review your draft order and pay its invoice.')
            }}
            {{ __('Tokens or your subscription start once payment is received.') }}
          </p>
          <p v-if="portalStatus === 'linked' || existingIdentityDetected" class="verified" data-testid="linked-identity-note">{{ __('You’re all set: your selected facilities have been added to your existing Tiberbu Express account.') }}</p>
          <p v-if="accountEmail" class="muted" style="margin-top: 12px" data-testid="success-account-email">{{ __('Tiberbu Express login: {0}', [accountEmail]) }}</p>
          <ul>
            <li v-for="item in submissions" :key="item.mfl_code">
              <b>{{ item.facility }}</b>
              <span style="display: flex; gap: 8px; align-items: center">
                <span v-if="provisioningStartedFor(item.mfl_code)" class="chip ok" data-testid="success-hmis-setup-started">{{ __('HMIS setup started') }}</span>
                <span class="mono muted">{{ item.mfl_code }}</span>
              </span>
            </li>
          </ul>
          <div v-if="provisioningStarted.length" class="verified" style="text-align: left; max-width: 520px; margin-inline: auto" data-testid="success-hmis-setup-note">
            <b>{{ __('We have started setting up your HMIS site') }}</b>
            <p>{{ __('Setup keeps running while you set your password. After you sign in, open your facility to follow its progress and get your HMIS site link and sign-in details.') }}</p>
          </div>
          <a class="btn primary" style="margin-top: 22px" href="/login?redirect-to=/cx-portal">{{ portalStatus === 'linked' || existingIdentityDetected ? __('Sign in to Tiberbu Express') : __('Go to sign in') }} →</a>
        </div>
      </section>
    </main>

    <Dialog v-model:open="termsDialogOpen" :title="termsSnapshot?.document || __('Terms and Conditions')" size="4xl">
      <div v-if="termsSnapshot?.rendered_html" class="prose prose-sm max-w-none prose-terms" v-html="termsSnapshot.rendered_html" />
    </Dialog>
  </div>
</template>

<script setup>
import '../../../../crm/public/css/value-express.css'
import './valueExpressOnboarding.css'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { call, Dialog } from 'frappe-ui'
import OtpCodeInput from '@/components/FacilityOnboarding/OtpCodeInput.vue'
import TiberbuWordmark from '@/components/FacilityOnboarding/TiberbuWordmark.vue'
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
import { FACILITY_PAGE_SIZE, facilityPage, filterFacilities } from '@/utils/facilityPager'
import { facilityId } from '@/utils/facilityId'
import { termsDocument, termsFileName } from '@/utils/termsDownload'
import {
  CUSTOM,
  customQuote,
  fixedForLevel,
  gridColumns,
  journeys,
  monthOneTokens,
  morePercent,
  parseCarriedChoice,
  periodLabel,
  perTokenRate,
} from '@/utils/valueExpress'

defineProps({
  networkSlug: { type: String, default: '' },
  facilityName: { type: String, default: '' },
  invitationToken: { type: String, default: '' },
})
const stage = ref('identity')
const busy = ref(false)
const catalogBusy = ref(false)
const catalogError = ref('')
const errorMessage = ref('')
const sessionToken = ref('')
const identityType = ref('national_id')
const identityNumber = ref('')
const identityPreview = ref({})
const tipOpen = ref(false)
const facilitySearch = ref('')
const facilityPageNumber = ref(1)
const facilityPageView = computed(() =>
  facilityPage(filterFacilities(facilities.value, facilitySearch.value), facilityPageNumber.value),
)
watch(facilitySearch, () => {
  facilityPageNumber.value = 1
})
const otp = ref('')
const facilities = ref([])
const selectedFacilities = ref([])
// "Get started" on the landing page carries a plan, package or Custom amount; a referral link may
// additionally carry a Partner Coupon (?partner_coupon=) that is validated on the first catalog load.
const carried = parseCarriedChoice(typeof window === 'undefined' ? '' : window.location.search)
const partnerId = ref(carried?.coupon || '')
// True until the URL-supplied coupon has been validated (or the user edits the field).
let urlCouponPending = Boolean(carried?.coupon)
const couponOpen = ref(false)
const couponPanelRef = ref(null)
const couponToggleRef = ref(null)
const couponInputRef = ref(null)
const catalog = ref({ network: null, packages: [], fixed_packages: [], custom_offer: null })
// Per facility: the plan ('flex' | 'fixed'), the Flex choice (an item code or CUSTOM) and a Custom amount.
const planSelections = ref({})
const flexChoice = ref({})
const customAmounts = ref({})
const activePricingFacilityId = ref('')
const accountEmail = ref('')
const termsAccepted = ref(false)
const termsSnapshot = ref(null)
const termsBusy = ref(false)
const termsDialogOpen = ref(false)
const agreeNudge = ref(false)
const submissions = ref([])
const portalStatus = ref('')
// HMIS setup is queued server-side as soon as onboarding commits.
const provisioningStarted = ref([])
const provisioningStartedFor = (mflCode) => provisioningStarted.value.includes(mflCode)
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
const deliveryChannelLabel = computed(() => (delivery.value.channel === 'sms' ? __('text message') : __('email')))
const expiryMinutes = computed(() => Math.max(1, Math.round((delivery.value.expires_in || 600) / 60)))
const selectable = (facility) => facility.onboarding_eligible === true && !facility.onboarding_blocked
const chosenFacilities = computed(() =>
  facilities.value.filter((item) => selectedFacilities.value.includes(item.facility_id)),
)
const activePricingFacility = computed(() => {
  if (!chosenFacilities.value.length) return null
  return chosenFacilities.value.find((item) => item.facility_id === activePricingFacilityId.value) || chosenFacilities.value[0]
})
const activeId = computed(() => activePricingFacility.value?.facility_id || '')

watch(
  chosenFacilities,
  (newChosen) => {
    if (newChosen.length && !newChosen.some((item) => item.facility_id === activePricingFacilityId.value)) {
      activePricingFacilityId.value = newChosen[0].facility_id
    }
  },
  { immediate: true },
)
// Complimentary tokens the server will add to each facility's first paid Flex package.
const welcomeBonusTokens = computed(() => Number(catalog.value.welcome_bonus_tokens) || 0)
const couponTokens = computed(() => Number(catalog.value.partner_coupon_tokens) || 0)
const couponApplied = computed(
  () =>
    partnerId.value.length === 6 &&
    couponTokens.value > 0 &&
    !catalogBusy.value &&
    !catalogError.value &&
    Boolean(catalog.value.network?.name),
)
const bonusLine = computed(() => {
  const parts = []
  if (welcomeBonusTokens.value) {
    parts.push(`+${welcomeBonusTokens.value.toLocaleString()} ${__('bonus tokens on your first purchase')}`)
  }
  if (couponApplied.value) {
    parts.push(`+${couponTokens.value.toLocaleString()} ${__('Partner Coupon tokens')}`)
  }
  return parts.join(' · ')
})
const accessTokens = computed(() => Number(catalog.value.calculator_config?.monthly_platform_fee) || 0)
const customOffer = computed(() => catalog.value.custom_offer || null)
const hasFixed = computed(() => (catalog.value.fixed_packages || []).length > 0)
const currency = computed(() => catalog.value.packages?.[0]?.currency || 'KES')
const entryPrice = computed(() =>
  Math.min(...(catalog.value.packages || []).map((pkg) => Number(pkg.price_ex_vat ?? pkg.price) || 0).filter(Boolean)),
)
const fixedFor = (id) => {
  const facility = facilities.value.find((item) => item.facility_id === id)
  return fixedForLevel(facility?.facility_level, catalog.value.fixed_packages)
}
const activeFixed = computed(() => fixedFor(activeId.value))
const activePlan = computed(() => planSelections.value[activeId.value] || 'flex')
const customAmountFor = (id) => customAmounts.value[id] ?? (Number(customOffer.value?.min_amount) || 0) + 1000
const activeCustomQuote = computed(() => customQuote(customAmountFor(activeId.value), customOffer.value))
const recommendedKey = computed(() => {
  if (carried?.plan === 'flex' && carried.package === CUSTOM && customOffer.value) return CUSTOM
  if (carried?.plan === 'flex' && catalog.value.packages?.some((pkg) => pkg.item_code === carried.package)) return carried.package
  const popular = (catalog.value.packages || []).find((pkg) => /popular/i.test(metricsOf(pkg).badge || ''))
  return popular?.item_code || ''
})
const carriedLabel = computed(() => {
  if (!carried) return ''
  if (carried.plan === 'fixed') return __('Value Express Fixed')
  if (carried.package === CUSTOM) return __('Value Express Flex Custom')
  const pkg = catalog.value.packages?.find((item) => item.item_code === carried.package)
  return pkg ? `${__('Value Express Flex')} ${pkg.display_name || pkg.item_code}` : __('Value Express Flex')
})

function metricsOf(pkg) {
  if (pkg?.coverage_metrics && typeof pkg.coverage_metrics === 'object') return pkg.coverage_metrics
  try {
    return JSON.parse(pkg?.coverage_metrics || '{}') || {}
  } catch {
    return {}
  }
}
function priceOf(pkg) {
  return Number(pkg?.price_ex_vat ?? pkg?.price ?? 0)
}
function currencyOf(pkg) {
  return pkg?.currency || currency.value
}

function openCoupon() {
  couponOpen.value = true
  nextTick(() => couponInputRef.value?.focus())
}
function closeCoupon() {
  if (!couponOpen.value) return
  couponOpen.value = false
  nextTick(() => couponToggleRef.value?.focus())
}
function onCouponKeydown(event) {
  if (event.key === 'Escape') closeCoupon()
}
function onCouponPointerDown(event) {
  if (couponPanelRef.value && !couponPanelRef.value.contains(event.target)) closeCoupon()
}
watch(couponOpen, (open) => {
  if (typeof document === 'undefined') return
  const method = open ? 'addEventListener' : 'removeEventListener'
  document[method]('keydown', onCouponKeydown)
  document[method]('pointerdown', onCouponPointerDown)
})
onBeforeUnmount(() => {
  if (typeof document === 'undefined') return
  document.removeEventListener('keydown', onCouponKeydown)
  document.removeEventListener('pointerdown', onCouponPointerDown)
})

// One facility is ready when its plan has a valid choice; Fixed always uses the facility's own level.
function isReady(id) {
  if ((planSelections.value[id] || 'flex') === 'fixed') return Boolean(fixedFor(id))
  const choice = flexChoice.value[id]
  if (choice === CUSTOM) return Boolean(customOffer.value) && customQuote(customAmountFor(id), customOffer.value).ok
  return Boolean(catalog.value.packages?.some((pkg) => pkg.item_code === choice))
}
const readyCount = computed(() => chosenFacilities.value.filter((facility) => isReady(facility.facility_id)).length)
const allPackagesSelected = computed(
  () => chosenFacilities.value.length > 0 && readyCount.value === chosenFacilities.value.length,
)
const nextFacility = computed(() =>
  chosenFacilities.value.find((facility) => facility.facility_id !== activeId.value && !isReady(facility.facility_id)),
)

// The package a facility will be quoted for, as the review and totals show it.
function selectedPackageFor(id) {
  if ((planSelections.value[id] || 'flex') === 'fixed') return fixedFor(id)
  const choice = flexChoice.value[id]
  if (choice !== CUSTOM) return catalog.value.packages?.find((pkg) => pkg.item_code === choice)
  const quote = customQuote(customAmountFor(id), customOffer.value)
  if (!quote.ok) return null
  const reference = catalog.value.packages?.[0] || {}
  const vatRate = Number(reference.vat_rate) || 0
  const vat = Math.round(quote.charge * vatRate) / 100
  return {
    item_code: customOffer.value.item_code,
    display_name: customOffer.value.display_name || __('Custom'),
    custom: true,
    token_quantity: quote.tokens,
    tier: quote.tier,
    rate: quote.rate,
    currency: customOffer.value.currency,
    price_ex_vat: quote.charge,
    vat_amount: vat,
    gross_total: Math.round((quote.charge + vat) * 100) / 100,
    vat_label: reference.vat_label || 'VAT',
  }
}
const totals = computed(() => {
  if (!allPackagesSelected.value) return null
  const packages = chosenFacilities.value.map((facility) => selectedPackageFor(facility.facility_id))
  if (packages.some((item) => !item)) return null
  const cur = packages[0]?.currency || 'KES'
  if (packages.some((item) => (item.currency || 'KES') !== cur)) return null
  return packages.reduce(
    (sum, item) => ({
      currency: cur,
      vatLabel: item.vat_label || sum.vatLabel || 'VAT',
      exVat: sum.exVat + priceOf(item),
      vat: sum.vat + Number(item.vat_amount || 0),
      gross: sum.gross + Number(item.gross_total ?? item.price_ex_vat ?? item.price ?? 0),
    }),
    { currency: cur, vatLabel: '', exVat: 0, vat: 0, gross: 0 },
  )
})
function choiceLabel(id) {
  if ((planSelections.value[id] || 'flex') === 'fixed') return fixedFor(id) ? __('Fixed · {0}', [fixedFor(id).facility_levels?.[0] || '']) : __('Fixed · not offered')
  const pkg = selectedPackageFor(id)
  if (!pkg) return __('Flex · choose a package')
  return pkg.custom ? __('Flex · Custom {0}', [money(customAmountFor(id), pkg.currency)]) : __('Flex · {0}', [pkg.display_name || pkg.item_code])
}
function reviewPlan(id) {
  const pkg = selectedPackageFor(id)
  if (!pkg) return { title: '', detail: '' }
  if ((planSelections.value[id] || 'flex') === 'fixed') {
    return { title: __('Value Express Fixed, {0}', [pkg.facility_levels?.[0] || pkg.display_name]), detail: __('Billed {0}', [__(periodLabel(pkg.billing_period))]) }
  }
  const access = accessTokens.value ? ` · ${__('{0} tokens/month system access', [accessTokens.value.toLocaleString()])}` : ''
  if (pkg.custom) {
    return {
      title: __('Value Express Flex Custom'),
      detail: __('{0} tokens at the {1} rate', [pkg.token_quantity.toLocaleString(), pkg.tier]) + access,
    }
  }
  const bonus = welcomeBonusTokens.value ? ` + ${welcomeBonusTokens.value.toLocaleString()} ${__('bonus')}` : ''
  return {
    title: __('Value Express Flex {0}', [pkg.display_name || pkg.item_code]),
    detail: `${Number(pkg.token_quantity || 0).toLocaleString()} ${__('tokens')}${bonus}${access}`,
  }
}
function setPlan(plan) {
  if (plan === 'fixed' && !activeFixed.value) return
  planSelections.value[activeId.value] = plan
}
function chooseFlex(choice) {
  planSelections.value[activeId.value] = 'flex'
  flexChoice.value[activeId.value] = choice
}
function setCustomAmount(value) {
  customAmounts.value[activeId.value] = Math.max(0, Math.floor(Number(value) || 0))
}
function goToFacility(id) {
  activePricingFacilityId.value = id
  nextTick(() => document.querySelector('.factabs')?.scrollIntoView({ block: 'start', behavior: 'smooth' }))
}
function changeFacility(id) {
  activePricingFacilityId.value = id
  stage.value = 'pricing'
}
// First visit to Packages: apply the landing page's choice where it fits; otherwise nothing is preselected.
function applyCarriedChoice() {
  for (const facility of chosenFacilities.value) {
    const id = facility.facility_id
    if (planSelections.value[id]) continue
    if (carried?.plan === 'fixed' && fixedFor(id)) {
      planSelections.value[id] = 'fixed'
      continue
    }
    planSelections.value[id] = 'flex'
    if (carried?.package === CUSTOM && customOffer.value) {
      flexChoice.value[id] = CUSTOM
      if (carried.amount) customAmounts.value[id] = carried.amount
    } else if (carried?.package && catalog.value.packages?.some((pkg) => pkg.item_code === carried.package)) {
      flexChoice.value[id] = carried.package
    }
  }
}

const reviewReady = computed(
  () =>
    Boolean(termsSnapshot.value?.content_hash) &&
    canAdvance('review', {
      accountEmail: accountEmail.value,
      packageSelectionsComplete: allPackagesSelected.value,
      hasTerms: Boolean(termsSnapshot.value?.content_hash),
      termsAccepted: termsAccepted.value,
    }),
)
watch(termsAccepted, (accepted) => {
  if (accepted) agreeNudge.value = false
})
const networkName = computed(() => catalog.value.network?.display_name || '')
const supportEmail = computed(() => catalog.value.network?.contact_email || '')
const catalogCurrent = computed(() => loadedCatalogPartnerId === partnerId.value && Boolean(catalog.value.network))
const STEP_TEXT = {
  identity: [__('Verify'), __('Confirm your details')],
  facilities: [__('Facility'), __('Select your facility')],
  pricing: [__('Package'), __('Choose your Value Express plan')],
  review: [__('Review'), __('Confirm and get started')],
}
const progressSteps = computed(() =>
  STEPS.map((step) => {
    const status = stepStatus(step.key, stage.value)
    return {
      key: step.key,
      label: STEP_TEXT[step.key][0],
      subtitle: STEP_TEXT[step.key][1],
      status,
      statusLabel: status === 'complete' ? __('complete') : status === 'current' ? __('current step') : __('upcoming'),
    }
  }),
)

function money(value, cur = 'KES', decimals = 0) {
  const num = Number(value || 0)
  return `${cur || 'KES'} ${num.toLocaleString('en-KE', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`
}
function unwrap(response) {
  return response?.message?.data || response?.data || response?.message || response || {}
}
async function request(method, args) {
  return unwrap(await call(`crm.api.facility_onboarding.${method}`, args))
}
function isSessionError(error) {
  return error?.exc_type === 'PermissionError' || /expired|session/i.test(error?.messages?.[0] || '')
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
    // A restart within the resend window reuses the code already sent.
    applyDelivery({ ...data.delivery, reused: Boolean(data.reused) })
    stage.value = 'otp'
  } catch (error) {
    errorMessage.value = error?.messages?.[0] || __('We could not verify those details. Please try again.')
  } finally {
    busy.value = false
  }
}
async function resendOtp() {
  errorMessage.value = ''
  otpError.value = ''
  busy.value = true
  try {
    const data = await request('resend_otp', { session_token: sessionToken.value })
    otp.value = ''
    applyDelivery(data.delivery)
  } catch (error) {
    sessionExpired.value = isSessionError(error)
    errorMessage.value = error?.messages?.[0] || __('We could not resend the code.')
  } finally {
    busy.value = false
  }
}
async function verifyOtp() {
  errorMessage.value = ''
  otpError.value = ''
  busy.value = true
  try {
    const data = await request('verify_otp', { session_token: sessionToken.value, otp: otp.value })
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
      const recovered = await request('retry_hfr', { session_token: sessionToken.value })
      if (recovered.state === 'hfr_pending') {
        hfrRetryPending.value = true
        hfrRetryExhausted.value = !recovered.retryable
      } else {
        acceptFacilities(recovered)
      }
      return
    } catch {
      otpError.value = error?.messages?.[0] || __('The code is incorrect or expired.')
    }
  } finally {
    busy.value = false
  }
}
function acceptFacilities(data) {
  identityPreview.value = data.identity || identityPreview.value
  accountEmail.value = data.account_email || ''
  facilities.value = data.facilities || []
  facilitySearch.value = ''
  facilityPageNumber.value = 1
  hfrRetryPending.value = false
  hfrRetryExhausted.value = false
  stage.value = 'facilities'
  stopResendTimer()
}
async function retryHfr() {
  errorMessage.value = ''
  busy.value = true
  try {
    const data = await request('retry_hfr', { session_token: sessionToken.value })
    if (data.state === 'hfr_pending') {
      hfrRetryPending.value = true
      hfrRetryExhausted.value = !data.retryable
    } else {
      acceptFacilities(data)
    }
  } catch (error) {
    sessionExpired.value = isSessionError(error)
    errorMessage.value = error?.messages?.[0] || __('We could not retry the facility lookup.')
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
  if (!selectedFacilities.value.length) return
  stage.value = 'pricing'
  loadCatalog()
}
async function loadCatalog(force = false) {
  const requestedPartnerId = partnerId.value
  if (!force && loadedCatalogPartnerId === requestedPartnerId) {
    applyCarriedChoice()
    return true
  }
  const requestId = ++catalogRequestId
  catalogError.value = ''
  catalogBusy.value = true
  catalog.value = { network: null, packages: [], fixed_packages: [], custom_offer: null }
  try {
    const nextCatalog = await request('get_catalog', { partner_id: requestedPartnerId })
    if (requestId !== catalogRequestId) return false
    catalog.value = nextCatalog
    loadedCatalogPartnerId = requestedPartnerId
    urlCouponPending = false
    applyCarriedChoice()
    return true
  } catch (error) {
    if (requestId !== catalogRequestId) return false
    // A coupon that arrived via the URL is validated exactly like typed entry; when it does not
    // resolve, drop it silently (the user did not type it) and reload the catalog without it.
    if (urlCouponPending && requestedPartnerId) {
      urlCouponPending = false
      partnerId.value = ''
      loadedCatalogPartnerId = null
      return loadCatalog(true)
    }
    catalog.value = { network: null, packages: [], fixed_packages: [], custom_offer: null }
    loadedCatalogPartnerId = null
    catalogError.value =
      error?.messages?.[0] || __('We couldn’t find that Partner Coupon. Check the six digits or ask your Network partner for help.')
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
  urlCouponPending = false
  catalogRequestId += 1
  catalogBusy.value = false
  catalogError.value = ''
  loadedCatalogPartnerId = null
  catalog.value = { network: null, packages: [], fixed_packages: [], custom_offer: null }
  if (!nextPartnerId || nextPartnerId.length === 6) loadCatalog(true)
}
function downloadTerms() {
  if (!termsSnapshot.value?.rendered_html) return
  const savedOn = new Date().toLocaleDateString(undefined, { dateStyle: 'long' })
  const blob = new Blob([termsDocument(termsSnapshot.value, savedOn)], { type: 'text/html' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = termsFileName(termsSnapshot.value.document)
  link.click()
  URL.revokeObjectURL(url)
}
async function loadSelfOnboardingTerms() {
  errorMessage.value = ''
  termsAccepted.value = false
  termsSnapshot.value = null
  termsBusy.value = true
  try {
    termsSnapshot.value = await request('get_self_onboarding_terms', { session_token: sessionToken.value })
    return true
  } catch (error) {
    errorMessage.value = error?.messages?.[0] || __('We could not load the current Terms and Conditions.')
    return false
  } finally {
    termsBusy.value = false
  }
}
async function continuePricing() {
  if (!allPackagesSelected.value || termsBusy.value || catalogBusy.value || catalogError.value || !catalogCurrent.value) return
  if (await loadSelfOnboardingTerms()) stage.value = 'review'
}
// What the server prices: a Flex or Fixed item code, or a Custom amount it re-prices itself.
function packageItemsPayload() {
  return Object.fromEntries(
    selectedFacilities.value.map((id) => {
      if ((planSelections.value[id] || 'flex') === 'fixed') return [id, fixedFor(id)?.item_code || '']
      if (flexChoice.value[id] === CUSTOM) return [id, { custom_amount: customAmountFor(id) }]
      return [id, flexChoice.value[id] || '']
    }),
  )
}
function conflictMessage(result) {
  if (result?.outcome === 'facility_level_ineligible') {
    const ineligible = new Set(result.ineligible_facility_ids || [])
    const eligibilityById = new Map((result.facility_eligibility || []).map((status) => [status.facility_id, status]))
    facilities.value = facilities.value.map((facility) =>
      eligibilityById.has(facility.facility_id) || ineligible.has(facility.facility_id)
        ? {
            ...facility,
            ...(eligibilityById.get(facility.facility_id) || {
              onboarding_eligible: false,
              facility_eligibility_reason: 'level_not_allowed',
            }),
          }
        : facility,
    )
    selectedFacilities.value = selectedFacilities.value.filter((facilityId) => !ineligible.has(facilityId))
    stage.value = 'facilities'
    return __('Facility level eligibility changed while you were onboarding. Review the facilities and continue with approved levels.')
  }
  if (result?.already_onboarded_facility_ids?.length) {
    const blocked = new Set(result.already_onboarded_facility_ids)
    const names = facilities.value
      .filter((facility) => blocked.has(facility.facility_id))
      .map((facility) => facility.facility_name || facility.mfl_code)
    facilities.value = facilities.value.map((facility) =>
      blocked.has(facility.facility_id)
        ? { ...facility, onboarding_blocked: true, onboarding_block_reason: 'already_onboarded' }
        : facility,
    )
    selectedFacilities.value = selectedFacilities.value.filter((facilityId) => !blocked.has(facilityId))
    stage.value = 'facilities'
    return `${__('Already onboarded and cannot be selected to proceed')}: ${names.join(', ')}`
  }
  if (result?.outcome === 'facility_review') {
    const allowed = new Set(result.allowed_facility_ids || [])
    const names = facilities.value
      .filter((facility) => selectedFacilities.value.includes(facility.facility_id) && !allowed.has(facility.facility_id))
      .map((facility) => facility.facility_name || facility.mfl_code)
    const selectedNames = names.length ? `: ${names.join(', ')}` : ''
    return `${__('One or more selected facilities already have a request with this Network')}${selectedNames}. ${__('Review your facility choices and try again.')}`
  }
  return ''
}
async function submit() {
  if (!termsAccepted.value) {
    // The confirm button stays focusable so a click explains what is missing.
    agreeNudge.value = true
    document.querySelector('[data-testid="terms-acceptance"]')?.focus()
    return
  }
  if (!reviewReady.value || busy.value) return
  errorMessage.value = ''
  registrationConflictDetected.value = false
  busy.value = true
  try {
    const conflict = await request('check_onboarding_conflicts', {
      session_token: sessionToken.value,
      partner_id: partnerId.value,
      selected_facility_ids: JSON.stringify(selectedFacilities.value),
    })
    if (conflict?.outcome === 'existing_identity' || conflict?.is_existing_identity) {
      existingIdentityDetected.value = true
    }
    const preflightMessage = conflictMessage(conflict)
    if (preflightMessage) {
      errorMessage.value = preflightMessage
      registrationConflictDetected.value = conflict?.outcome === 'facility_review'
      return
    }
    if (conflict?.outcome !== 'new' && conflict?.outcome !== 'existing_identity') {
      errorMessage.value = __('We could not verify this onboarding selection. Please try again.')
      return
    }
    const items = packageItemsPayload()
    const firstItem = items[selectedFacilities.value[0]]
    const data = await request('submit_onboarding', {
      session_token: sessionToken.value,
      partner_id: partnerId.value,
      selected_facility_ids: JSON.stringify(selectedFacilities.value),
      package_item_code: typeof firstItem === 'string' ? firstItem : '',
      facility_package_items: JSON.stringify(items),
      account_email: accountEmail.value,
      terms_accepted: termsAccepted.value ? 1 : 0,
      accepted_terms_hash: termsSnapshot.value.content_hash,
    })
    if (data?.outcome === 'existing_identity' || data?.is_existing_identity || data?.portal_status === 'linked') {
      existingIdentityDetected.value = true
      portalStatus.value = data?.portal_status || 'linked'
    }
    const submitConflict = conflictMessage(data)
    if (submitConflict) {
      errorMessage.value = submitConflict
      registrationConflictDetected.value = data?.outcome === 'facility_review'
      return
    }
    if (data?.outcome && data.outcome !== 'new' && data.outcome !== 'existing_identity') {
      errorMessage.value = __('We could not verify this onboarding selection. Please try again.')
      return
    }
    submissions.value = data.enrollments || data.submissions || []
    provisioningStarted.value = data.provisioning?.state === 'started' ? data.provisioning.facilities || [] : []
    if (data.portal_status) {
      portalStatus.value = data.portal_status
    }
    stage.value = 'success'
  } catch (error) {
    sessionExpired.value = isSessionError(error)
    const message = error?.messages?.[0] || __('We could not complete onboarding. Please try again.')
    if (/terms/i.test(message)) {
      const refreshed = await loadSelfOnboardingTerms()
      if (refreshed) stage.value = 'review'
      errorMessage.value = refreshed ? __('The Terms have changed. Review and accept the updated Terms before submitting.') : message
    } else {
      errorMessage.value = message
    }
  } finally {
    busy.value = false
  }
}
function reset() {
  stage.value = 'identity'
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
  catalog.value = { network: null, packages: [], fixed_packages: [], custom_offer: null }
  catalogRequestId += 1
  catalogBusy.value = false
  catalogError.value = ''
  loadedCatalogPartnerId = null
  planSelections.value = {}
  flexChoice.value = {}
  customAmounts.value = {}
  termsSnapshot.value = null
  termsAccepted.value = false
  accountEmail.value = ''
}
</script>
