<template>
  <div
    class="flex h-full min-w-0 flex-col overflow-x-hidden overflow-y-auto px-3 pb-3 sm:px-10 sm:pb-5"
  >
    <!-- ── APPLICANT HERO CARD (OIS deals only) ──────────────────────────── -->
    <div
      v-if="dealDoc?.optin_submission"
      class="mt-4 rounded-xl border-2 border-outline-gray-2 bg-surface-white dark:bg-surface-gray-1 p-5"
    >
      <!-- Loading skeleton -->
      <div v-if="oisResource.loading" class="space-y-2">
        <div
          v-for="n in 4"
          :key="n"
          class="h-4 animate-pulse rounded bg-surface-gray-2"
        />
      </div>

      <template v-else>
        <!-- Header row: OIS ref + OTP Verified chip -->
        <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
          <span class="text-xs text-ink-gray-4 font-mono">{{
            dealDoc.optin_submission
          }}</span>
          <span
            class="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400"
          >
            {{ __('OTP Verified') }} ✓
          </span>
        </div>

        <!-- Name -->
        <p class="text-xl font-bold text-ink-gray-9">
          {{
            [oisContact?.first_name, oisContact?.last_name]
              .filter(Boolean)
              .join(' ') || '—'
          }}
        </p>

        <!-- Role · Organisation -->
        <p
          v-if="oisContact?.role || oisContact?.organisation"
          class="mt-0.5 text-sm text-ink-gray-5"
        >
          {{
            [oisContact?.role, oisContact?.organisation]
              .filter(Boolean)
              .join(' · ')
          }}
        </p>

        <!-- Email · Phone + Email Applicant button -->
        <div class="mt-2 flex flex-wrap items-center justify-between gap-3">
          <div class="flex flex-wrap items-center gap-3">
            <a
              v-if="oisContact?.email"
              :href="'mailto:' + oisContact.email"
              class="text-ink-blue-6 hover:underline font-medium text-sm"
              >{{ oisContact.email }}</a
            >
            <span v-if="oisContact?.mobile_no" class="text-ink-gray-6 text-sm">
              {{ oisContact.mobile_no }}
            </span>
          </div>
          <Button
            v-if="oisContact?.email"
            size="sm"
            variant="subtle"
            @click="emailApplicant"
          >
            {{ __('Email Applicant') }}
          </Button>
        </div>
      </template>
    </div>

    <!-- ── FACILITIES TABLE (OIS deals only, shown when facilities exist) ── -->
    <div v-if="oisFacilities.length" class="mt-3">
      <div
        class="hidden overflow-x-auto rounded-lg border border-outline-gray-2 sm:block"
      >
        <table class="w-full text-xs">
          <thead class="bg-surface-gray-1 text-ink-gray-5">
            <tr>
              <th class="px-3 py-2 text-left font-medium">
                {{ __('MFL Code') }}
              </th>
              <th class="px-3 py-2 text-left font-medium">
                {{ __('Facility Name') }}
              </th>
              <th class="px-3 py-2 text-left font-medium">
                {{ __('KEPH Level') }}
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-outline-elevation-2">
            <tr
              v-for="f in oisFacilities"
              :key="f.mfl_code"
              class="even:bg-surface-gray-1"
            >
              <td class="px-3 py-2 font-mono text-ink-gray-7">
                {{ f.mfl_code }}
              </td>
              <td class="px-3 py-2 text-ink-gray-8">{{ f.facility_name }}</td>
              <td class="px-3 py-2 text-ink-gray-6">{{ f.keph_level }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="space-y-2 sm:hidden">
        <article
          v-for="f in oisFacilities"
          :key="`mobile-${f.mfl_code}`"
          class="rounded-lg border border-outline-gray-2 bg-surface-white px-3 py-3 dark:bg-surface-gray-1"
        >
          <p class="text-sm font-semibold text-ink-gray-9">
            {{ f.facility_name || __('Unnamed facility') }}
          </p>
          <div
            class="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-gray-5"
          >
            <span v-if="f.mfl_code" class="font-mono"
              >MFL {{ f.mfl_code }}</span
            >
            <span v-if="f.keph_level">{{ f.keph_level }}</span>
          </div>
        </article>
      </div>
    </div>

    <!-- Finance Cockpit handoff banner -->
    <div
      v-if="acceptedQuote"
      class="mt-4 flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-4 py-3 dark:border-green-800 dark:bg-green-900/20"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        class="h-4 w-4 flex-shrink-0 text-green-600 dark:text-green-400"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <polyline points="20 6 9 17 4 12" />
      </svg>
      <span class="text-sm text-green-800 dark:text-green-300">
        {{ __('Quote accepted —') }}
        <strong>{{ acceptedQuote.erpnext_sales_invoice }}</strong>
        {{ __('created.') }}
        <a
          href="/finance-cockpit#/receivables/invoices"
          target="_blank"
          class="ml-1 underline font-medium"
          >{{ __('View in Finance Cockpit → Receivables → AR Invoices') }}</a
        >
      </span>
    </div>

    <!-- ── QUOTES SECTION ─────────────────────────────────────────────────── -->
    <div class="mt-4 flex flex-wrap items-center justify-between gap-3">
      <h2 class="text-base font-semibold text-ink-gray-9">
        {{ __('Quotes') }}
      </h2>

      <!-- Non-OIS deals: start a new blank quote (OIS deals auto-build) -->
      <div v-if="!isOis" class="flex items-center gap-2">
        <Button
          v-if="dealDoc?.optin_network && !quotes.length"
          variant="subtle"
          @click="openInvitationDialog"
          >{{ __('Send Opt-In Invite') }}</Button
        >
        <Button variant="solid" :loading="creating" @click="createQuote">
          <template #prefix>
            <svg
              xmlns="http://www.w3.org/2000/svg"
              class="h-4 w-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </template>
          {{ __('New Quote') }}
        </Button>
      </div>
    </div>

    <!-- ═══ OIS DEALS: yearly quotation bundle ═══ -->
    <template v-if="isOis">
      <!-- The approval number is the sum of the current yearly quotations. It
           intentionally sits above the detail cards so the CRM reviewer sees
           one VAT-aware commitment before comparing individual years. -->
      <section
        v-if="oisCommitment.yearCount"
        class="mt-4 rounded-xl border-2 border-outline-red-4 bg-surface-white p-5 dark:bg-surface-gray-1"
      >
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p
              class="text-xs font-semibold uppercase tracking-wider text-ink-gray-5"
            >
              {{ __('Total contract commitment · incl. VAT') }}
            </p>
            <p class="mt-1 text-3xl font-black tracking-tight text-ink-gray-9">
              {{ fmtKes(oisCommitment.grandTotal) }}
            </p>
            <p class="mt-1 text-sm text-ink-gray-5">
              {{
                __('Current total across {0} yearly quotation(s).', [
                  oisCommitment.yearCount,
                ])
              }}
            </p>
          </div>
          <div
            class="min-w-[210px] rounded-lg bg-surface-gray-1 px-3 py-2 text-sm dark:bg-surface-gray-2"
          >
            <div class="flex justify-between gap-4">
              <span class="text-ink-gray-5">{{ __('Excl. VAT') }}</span>
              <span class="font-semibold text-ink-gray-8">{{
                fmtKes(oisCommitment.netTotal)
              }}</span>
            </div>
            <div class="mt-1 flex justify-between gap-4">
              <span class="text-ink-gray-5">{{ __('VAT') }}</span>
              <span class="font-semibold text-ink-gray-8">{{
                fmtKes(oisCommitment.vatAmount)
              }}</span>
            </div>
            <div
              class="mt-1 border-t border-outline-elevation-2 pt-1 text-xs text-ink-gray-5"
            >
              {{ __('Year 1 incl. VAT') }}:
              {{ fmtKes(oisCommitment.yearOneGrandTotal) }}
            </div>
          </div>
        </div>
        <p class="mt-3 text-xs text-ink-gray-5">
          {{
            __(
              'Line-item rates are exclusive of VAT. VAT is shown separately and totals are recalculated from the current quotation bundle.',
            )
          }}
        </p>
      </section>

      <section
        v-if="quotes.length > 1"
        class="mt-4 rounded-xl border border-outline-gray-2 bg-surface-white p-4 dark:bg-surface-gray-1"
      >
        <div class="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p class="text-sm font-semibold text-ink-gray-9">
              {{ __('Yearly quotations') }}
            </p>
            <p class="mt-0.5 text-xs text-ink-gray-5">
              {{
                __(
                  'Each year has its own subscription quotation. The contract and signing process remain one agreement.',
                )
              }}
            </p>
          </div>
          <span
            class="rounded-full bg-surface-gray-2 px-2 py-1 text-xs font-semibold text-ink-gray-6"
          >
            {{ __('{0} years', [quotes.length]) }}
          </span>
        </div>
        <div class="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          <button
            v-for="(q, index) in quotes"
            :key="`ois-year-${q.name}`"
            type="button"
            class="rounded-lg border px-3 py-3 text-left transition-colors"
            :class="
              primaryQuoteName === q.name
                ? 'border-outline-red-4 bg-surface-gray-1 dark:bg-surface-gray-2'
                : 'border-outline-gray-2 hover:bg-surface-gray-1 dark:hover:bg-surface-gray-2'
            "
            @click="selectedOisQuote = q.name"
          >
            <div class="flex items-center justify-between gap-2">
              <span class="text-sm font-semibold text-ink-gray-9">
                {{ __('Year {0}', [quoteYear(q, index)]) }}
              </span>
              <span :class="pillClass(q)">{{ __(q.status) }}</span>
            </div>
            <p class="mt-1 truncate text-xs text-ink-gray-5">
              {{ quoteContractScheduleSummary(q, index) }}
            </p>
            <p class="mt-2 text-sm font-semibold text-ink-gray-9">
              {{ fmtKes(q.grand_total) }}
              <span class="text-xs font-normal text-ink-gray-5">{{
                __('incl. VAT')
              }}</span>
            </p>
            <p class="mt-0.5 text-xs text-ink-gray-5">
              {{ fmtKes(q.net_total) }} {{ __('excl. VAT') }}
            </p>
            <p class="mt-1 text-[11px] text-ink-gray-5">{{ q.name }}</p>
          </button>
        </div>
      </section>

      <!-- Quote exists → edit negotiated pricing inline, right here -->
      <QuotePanel
        v-if="primaryQuoteName"
        :deal-id="dealId"
        :quote-name="primaryQuoteName"
        @saved="onQuoteSaved"
      />

      <!-- No quote yet → auto-building from opt-in data -->
      <div v-else class="mt-10 flex flex-col items-center gap-3 text-center">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          class="h-10 w-10 text-ink-gray-3"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path
            d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"
          />
          <polyline points="14 2 14 8 20 8" />
        </svg>
        <div
          v-if="buildQuoteResource.loading"
          class="flex items-center gap-2 text-sm text-ink-gray-6"
        >
          <svg
            class="h-4 w-4 animate-spin"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              class="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              stroke-width="4"
            />
            <path
              class="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8v8z"
            />
          </svg>
          {{ __('Building quote from opt-in data…') }}
        </div>
        <div
          v-else-if="buildError"
          class="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-400"
        >
          {{ __('Quote could not be auto-generated — contact support.') }}
        </div>
        <p v-else class="text-xs text-ink-gray-4">
          {{ __('Quote will be built from this opt-in submission.') }}
        </p>
      </div>
    </template>

    <!-- ═══ NON-OIS DEALS: quote list + inline editor ═══ -->
    <template v-else>
      <!-- Loading skeleton -->
      <div v-if="quotesResource.loading" class="mt-6 space-y-2">
        <div
          v-for="n in 2"
          :key="n"
          class="h-12 animate-pulse rounded-lg bg-surface-gray-2"
        />
      </div>

      <!-- Empty state -->
      <div
        v-else-if="!quotes.length"
        class="mt-16 flex flex-col items-center gap-3 text-center"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          class="h-12 w-12 text-ink-gray-3"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path
            d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"
          />
          <polyline points="14 2 14 8 20 8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
          <polyline points="10 9 9 9 8 9" />
        </svg>
        <p class="text-sm font-medium text-ink-gray-5">
          {{ __('No quotes yet') }}
        </p>
        <p class="text-xs text-ink-gray-4">
          {{ __('Create a quote to send a formal proposal to this customer.') }}
        </p>
        <Button
          class="mt-2"
          variant="solid"
          :loading="creating"
          @click="createQuote"
        >
          {{ __('+ Create Quote') }}
        </Button>
      </div>

      <!-- Quote list table -->
      <div v-else class="mt-4">
        <div
          class="hidden overflow-x-auto rounded-lg border border-outline-elevation-2 sm:block"
        >
          <table class="w-full text-sm">
            <thead
              class="bg-surface-gray-1 text-xs uppercase tracking-wide text-ink-gray-5"
            >
              <tr>
                <th class="px-4 py-2.5 text-left font-medium">
                  {{ __('Quote #') }}
                </th>
                <th class="px-4 py-2.5 text-left font-medium">
                  {{ __('Created') }}
                </th>
                <th class="px-4 py-2.5 text-left font-medium">
                  {{ __('Valid Until') }}
                </th>
                <th class="px-4 py-2.5 text-right font-medium">
                  {{ __('Grand Total (incl. VAT)') }}
                </th>
                <th class="px-4 py-2.5 text-left font-medium">
                  {{ __('Payment') }}
                </th>
                <th class="px-4 py-2.5 text-left font-medium">
                  {{ __('Status') }}
                </th>
                <th class="px-4 py-2.5 text-right font-medium">
                  {{ __('Actions') }}
                </th>
              </tr>
            </thead>
            <tbody class="divide-y divide-outline-elevation-2">
              <tr
                v-for="q in quotes"
                :key="q.name"
                class="cursor-pointer transition-colors"
                :class="
                  selectedQuote === q.name
                    ? 'bg-surface-gray-2 dark:bg-surface-gray-3'
                    : 'hover:bg-surface-gray-1'
                "
                @click="selectQuote(q.name)"
              >
                <td class="px-4 py-3 font-medium text-ink-gray-9">
                  {{ q.name }}
                </td>
                <td class="px-4 py-3">
                  <span class="text-ink-gray-8 font-medium">{{
                    timeAgo(q.creation ?? q.quote_date)
                  }}</span>
                  <div class="text-xs text-ink-gray-4">
                    {{ formatDate(q.quote_date) }}
                  </div>
                </td>
                <td
                  class="px-4 py-3"
                  :class="
                    isExpired(q)
                      ? 'text-red-500 font-medium'
                      : 'text-ink-gray-6'
                  "
                >
                  {{ formatDate(q.valid_until) }}
                </td>
                <td class="px-4 py-3 text-right font-semibold text-ink-gray-9">
                  {{ fmtKes(q.grand_total) }}
                </td>
                <td class="px-4 py-3 text-ink-gray-6 text-xs">
                  {{ q.payment_terms }}
                </td>
                <td class="px-4 py-3">
                  <span :class="pillClass(q)">
                    {{ isExpired(q) ? __('Expired') : __(q.status) }}
                  </span>
                </td>
                <td class="px-4 py-3 text-right" @click.stop>
                  <div class="flex items-center justify-end gap-1.5">
                    <Button
                      size="sm"
                      variant="ghost"
                      @click="selectQuote(q.name)"
                      >{{ __('Edit') }}</Button
                    >
                    <Button
                      v-if="q.status === 'Draft' || q.status === 'Sent'"
                      size="sm"
                      variant="ghost"
                      @click="sendQuote(q.name)"
                      :loading="sendingName === q.name"
                      >{{ __('Send') }}</Button
                    >
                    <Button
                      v-if="q.status === 'Sent'"
                      size="sm"
                      variant="ghost"
                      theme="green"
                      @click="acceptQuote(q.name)"
                      :loading="actionName === q.name"
                      >{{ __('Accept') }}</Button
                    >
                    <Button
                      v-if="q.status === 'Sent'"
                      size="sm"
                      variant="ghost"
                      theme="red"
                      @click="confirmReject(q.name)"
                      >{{ __('Reject') }}</Button
                    >
                    <Button
                      size="sm"
                      variant="ghost"
                      @click="downloadPdf(q.name)"
                      >{{ __('PDF') }}</Button
                    >
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="space-y-2 sm:hidden">
          <article
            v-for="q in quotes"
            :key="`mobile-${q.name}`"
            class="rounded-lg border border-outline-elevation-2 bg-surface-white p-3 dark:bg-surface-gray-1"
            :class="
              selectedQuote === q.name
                ? 'border-outline-red-4 bg-surface-gray-1 dark:bg-surface-gray-2'
                : ''
            "
          >
            <button
              type="button"
              class="flex w-full items-start justify-between gap-3 text-left"
              @click="selectQuote(q.name)"
            >
              <span class="min-w-0">
                <span
                  class="block truncate text-sm font-semibold text-ink-gray-9"
                >
                  {{ q.name }}
                </span>
                <span class="mt-0.5 block text-xs text-ink-gray-5">
                  {{ formatDate(q.quote_date) }} ·
                  {{ timeAgo(q.creation ?? q.quote_date) }}
                </span>
              </span>
              <span :class="pillClass(q)" class="shrink-0">
                {{ isExpired(q) ? __('Expired') : __(q.status) }}
              </span>
            </button>
            <div
              class="mt-3 flex items-center justify-between gap-3 border-t border-outline-elevation-2 pt-2"
            >
              <div>
                <span class="block text-sm font-semibold text-ink-gray-9">
                  {{ fmtKes(q.grand_total) }} {{ __('incl. VAT') }}
                </span>
                <span class="block text-xs text-ink-gray-5">
                  {{ fmtKes(q.net_total) }} {{ __('excl. VAT') }}
                </span>
              </div>
              <div class="flex flex-wrap justify-end gap-1.5" @click.stop>
                <Button size="sm" variant="ghost" @click="selectQuote(q.name)">
                  {{ __('Edit') }}
                </Button>
                <Button
                  v-if="q.status === 'Draft' || q.status === 'Sent'"
                  size="sm"
                  variant="ghost"
                  @click="sendQuote(q.name)"
                  :loading="sendingName === q.name"
                >
                  {{ __('Send') }}
                </Button>
                <Button
                  v-if="q.status === 'Sent'"
                  size="sm"
                  variant="ghost"
                  theme="green"
                  @click="acceptQuote(q.name)"
                  :loading="actionName === q.name"
                >
                  {{ __('Accept') }}
                </Button>
                <Button
                  v-if="q.status === 'Sent'"
                  size="sm"
                  variant="ghost"
                  theme="red"
                  @click="confirmReject(q.name)"
                >
                  {{ __('Reject') }}
                </Button>
                <Button size="sm" variant="ghost" @click="downloadPdf(q.name)">
                  {{ __('PDF') }}
                </Button>
              </div>
            </div>
          </article>
        </div>
      </div>

      <!-- Inline editor for the selected quote (universal QuotePanel) -->
      <QuotePanel
        v-if="selectedQuote"
        :deal-id="dealId"
        :quote-name="selectedQuote"
        @saved="onQuoteSaved"
      />
      <div
        v-if="selectedQuoteData?.status === 'Draft'"
        class="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-outline-gray-2 bg-surface-gray-1 px-4 py-3 dark:bg-surface-gray-2"
      >
        <div>
          <p class="text-sm font-medium text-ink-gray-8">
            {{ __('Ready to submit the Opt-In summary?') }}
          </p>
          <p class="mt-0.5 text-xs text-ink-gray-5">
            {{
              __(
                'This records the finalized quote against this Deal for contracting without creating a duplicate Deal.',
              )
            }}
          </p>
        </div>
        <Button variant="solid" @click="openSummaryDialog">
          {{ __('Submit Opt-In Summary') }}
        </Button>
      </div>
    </template>
    <!-- ═══ end non-OIS branch ═══ -->

    <!-- Reject confirmation dialog -->
    <Dialog
      v-model="showRejectDialog"
      :options="{ title: __('Reject this quote?'), size: 'sm' }"
    >
      <template #body-content>
        <p class="text-sm text-ink-gray-6">
          {{
            __(
              'This will set the quote status to Rejected. A new version will be needed.',
            )
          }}
        </p>
      </template>
      <template #actions>
        <Button variant="subtle" @click="showRejectDialog = false">{{
          __('Cancel')
        }}</Button>
        <Button
          variant="solid"
          theme="red"
          :loading="actionName !== null"
          @click="doReject"
        >
          {{ __('Confirm Reject') }}
        </Button>
      </template>
    </Dialog>

    <Dialog
      v-model="showInvitationDialog"
      :options="{ title: __('Send Opt-In Invitation'), size: 'md' }"
    >
      <template #body-content>
        <div class="space-y-4">
          <p class="text-sm text-ink-gray-6">
            {{
              __(
                'Send this Deal contact a secure link to review their facilities, confirm the negotiated pricing, and accept the agreement.',
              )
            }}
          </p>
          <div
            class="rounded-lg bg-surface-gray-2 p-3 text-sm dark:bg-surface-gray-3"
          >
            <div class="flex justify-between gap-4">
              <span class="text-ink-gray-6">{{ __('Network') }}</span
              ><span class="font-medium text-ink-gray-9">{{
                linkedNetworkName
              }}</span>
            </div>
            <div class="mt-2 flex justify-between gap-4">
              <span class="text-ink-gray-6">{{ __('Recipient') }}</span
              ><span class="font-medium text-ink-gray-9">{{
                dealDoc?.email || __('No primary email')
              }}</span>
            </div>
          </div>
          <FormControl
            v-model="invitationPriceList"
            type="select"
            :label="__('Contract schedule')"
            :options="priceListOptions"
            :description="
              __(
                'The recipient sees this contract schedule. It is locked into their invitation and does not change the Network default.',
              )
            "
          />
          <p v-if="invitationError" class="text-sm text-ink-red-6">
            {{ invitationError }}
          </p>
        </div>
      </template>
      <template #actions>
        <Button
          variant="subtle"
          :disabled="sendingInvitation"
          @click="showInvitationDialog = false"
          >{{ __('Cancel') }}</Button
        >
        <Button
          variant="solid"
          :disabled="!invitationPriceList"
          :loading="sendingInvitation"
          @click="sendInvitation"
          >{{ __('Send invitation') }}</Button
        >
      </template>
    </Dialog>

    <Dialog
      v-model="showOptInSummaryDialog"
      :options="{ title: __('Submit Opt-In Summary'), size: 'md' }"
    >
      <template #body-content>
        <div class="space-y-4">
          <p class="text-sm text-ink-gray-6">
            {{
              __(
                'Confirm the network for this finalized quote. The summary will be available to the contracting flow on this Deal.',
              )
            }}
          </p>
          <FormControl
            v-model="summaryNetwork"
            type="select"
            :label="__('Opt-In Network')"
            :options="networkOptions"
            :description="
              __(
                'The network determines the portal branding, contract schedule, and network signatories.',
              )
            "
          />
          <div
            class="rounded-lg bg-surface-gray-2 p-3 text-sm dark:bg-surface-gray-3"
          >
            <div class="flex justify-between gap-4">
              <span class="text-ink-gray-6">{{ __('Quote') }}</span
              ><span class="font-medium text-ink-gray-9">{{
                selectedQuote
              }}</span>
            </div>
            <div class="mt-2 flex justify-between gap-4">
              <span class="text-ink-gray-6">{{
                __('Quote total (incl. VAT)')
              }}</span
              ><span class="font-medium text-ink-gray-9">{{
                fmtKes(selectedQuoteData?.grand_total)
              }}</span>
            </div>
          </div>
          <p v-if="summaryError" class="text-sm text-ink-red-6">
            {{ summaryError }}
          </p>
        </div>
      </template>
      <template #actions>
        <Button
          variant="subtle"
          :disabled="submittingSummary"
          @click="showOptInSummaryDialog = false"
          >{{ __('Cancel') }}</Button
        >
        <Button
          variant="solid"
          :disabled="!summaryNetwork"
          :loading="submittingSummary"
          @click="submitOptInSummary"
          >{{ __('Submit Summary') }}</Button
        >
      </template>
    </Dialog>

    <!-- Contracting panel — mounted below the quotes section -->
    <ContractingPanel
      :deal-id="dealId"
      :ois-doc="oisResource.data ?? null"
      :lifecycle="lifecycle"
      @lifecycle-reload="onLifecycleReload"
      @email-dispatched="emit('email-dispatched')"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { createResource, Button, Dialog, FormControl, toast } from 'frappe-ui'
import ContractingPanel from './ContractingPanel.vue'
import QuotePanel from './QuotePanel.vue'

const props = defineProps({
  dealId: { type: String, required: true },
})

const emit = defineEmits(['email-dispatched'])

const route = useRoute()

// ── Deal doc ─────────────────────────────────────────────────────────────────

const dealDocResource = createResource({
  url: 'frappe.client.get',
  makeParams: () => ({ doctype: 'CRM Deal', name: props.dealId }),
  auto: true,
})
const dealDoc = computed(() => dealDocResource.data ?? null)

// OIS-sourced deals render the quote inline (no wizard overlay)
const isOis = computed(() => !!dealDoc.value?.optin_submission)
const selectedOisQuote = ref(null)
const primaryQuoteName = computed(
  () =>
    (selectedOisQuote.value &&
    quotes.value.some((q) => q.name === selectedOisQuote.value)
      ? selectedOisQuote.value
      : quotes.value[0]?.name) ??
    lifecycle.value?.quotation?.name ??
    null,
)

function onQuoteSaved() {
  quotesResource.reload()
  lifecycleResource.reload()
}

// ── Lifecycle (fetched here, passed down to ContractingPanel) ─────────────────

const lifecycleResource = createResource({
  url: 'crm.api.lifecycle.get_deal_lifecycle',
  makeParams: () => ({ deal: props.dealId }),
  auto: true,
})
const lifecycle = computed(() => lifecycleResource.data ?? null)

function onLifecycleReload() {
  lifecycleResource.reload()
}

// ── OIS submission ────────────────────────────────────────────────────────────

const oisResource = createResource({
  url: 'frappe.client.get',
  makeParams: () => ({
    doctype: 'CRM Opt-In Submission',
    name: dealDoc.value?.optin_submission ?? '',
  }),
})

watch(
  () => dealDoc.value?.optin_submission,
  (submissionRef) => {
    if (submissionRef) oisResource.reload()
  },
  { immediate: true },
)

const oisRawJson = computed(() => {
  const raw = oisResource.data?.raw_json
  if (!raw) return {}
  try {
    return JSON.parse(raw)
  } catch {
    return {}
  }
})

const oisContact = computed(() => oisRawJson.value?.contact ?? null)
const oisFacilities = computed(() => oisRawJson.value?.facilities ?? [])
const oisPricingPlans = computed(() => oisRawJson.value?.pricing_plans ?? [])

function quoteContractScheduleSummary(quote, index) {
  const year = quoteYear(quote, index)
  const plan = oisPricingPlans.value.find(
    (item) => Number(item?.year_number) === Number(year),
  )
  const schedules = [
    ...new Set(
      (plan?.facilities ?? [])
        .map((facility) => facility?.price_list || plan?.price_list)
        .filter(Boolean),
    ),
  ]
  if (schedules.length === 1) return schedules[0]
  if (schedules.length > 1)
    return __('{0} facility contract schedules', [schedules.length])
  return quote.selling_price_list || __('Configured contract schedule')
}

// ── Email applicant ───────────────────────────────────────────────────────────

function emailApplicant() {
  const email = oisContact.value?.email
  if (!email) return
  const oisRef = dealDoc.value?.optin_submission ?? ''
  const subject = `Re: Your CareverseHIMS Opt-In Application [${oisRef}]`
  window.open(
    `mailto:${email}?subject=${encodeURIComponent(subject)}`,
    '_blank',
  )
}

// ── Quotes ────────────────────────────────────────────────────────────────────

const quotesResource = createResource({
  url: 'crm.api.quotes.list_quotes',
  makeParams: () => ({ deal: props.dealId }),
  auto: true,
})
const quotes = computed(() => quotesResource.data ?? [])

const oisCommitment = computed(() => {
  const yearlyQuotes = quotes.value.filter(
    (quote) => quote.crm_optin_year || isOis.value,
  )
  if (yearlyQuotes.length) {
    const netTotal = yearlyQuotes.reduce(
      (total, quote) => total + Number(quote.net_total ?? 0),
      0,
    )
    const vatAmount = yearlyQuotes.reduce(
      (total, quote) => total + Number(quote.vat_amount ?? 0),
      0,
    )
    const grandTotal = yearlyQuotes.reduce(
      (total, quote) => total + Number(quote.grand_total ?? 0),
      0,
    )
    return {
      yearCount: yearlyQuotes.length,
      netTotal,
      vatAmount,
      grandTotal,
      yearOneGrandTotal: Number(yearlyQuotes[0]?.grand_total ?? 0),
    }
  }

  const commitment = lifecycle.value?.quotation_commitment
  if (commitment?.year_count) {
    const plans = oisPricingPlans.value
    return {
      yearCount: Number(commitment.year_count),
      netTotal: Number(commitment.net_total ?? 0),
      vatAmount: Number(commitment.vat_amount ?? 0),
      grandTotal: Number(commitment.grand_total ?? 0),
      yearOneGrandTotal: Number(plans[0]?.grand_total_annual ?? 0),
    }
  }

  const plans = oisPricingPlans.value
  return {
    yearCount: plans.length,
    netTotal: plans.reduce(
      (total, plan) => total + Number(plan.subtotal_annual ?? 0),
      0,
    ),
    vatAmount: plans.reduce(
      (total, plan) => total + Number(plan.vat_annual ?? 0),
      0,
    ),
    grandTotal: plans.reduce(
      (total, plan) => total + Number(plan.grand_total_annual ?? 0),
      0,
    ),
    yearOneGrandTotal: Number(plans[0]?.grand_total_annual ?? 0),
  }
})

watch(
  [isOis, quotes],
  ([ois, list]) => {
    if (!ois) {
      selectedOisQuote.value = null
      return
    }
    if (!list.some((quote) => quote.name === selectedOisQuote.value)) {
      selectedOisQuote.value = list[0]?.name ?? null
    }
  },
  { immediate: true },
)

function quoteYear(quote, index) {
  return Number(quote?.crm_optin_year || index + 1)
}

const acceptedQuote = computed(() =>
  quotes.value.find((q) => q.status === 'Accepted' && q.erpnext_sales_invoice),
)

// ── Auto-build Quote from OIS (Case A) ───────────────────────────────────────

const buildAttempted = ref(false)
const buildError = ref(null)

const buildQuoteResource = createResource({
  url: 'crm.api.optin.build_ois_quote',
  onSuccess: () => {
    quotesResource.reload()
    lifecycleResource.reload()
  },
  onError: (e) => {
    buildError.value = e?.message ?? 'Auto-build failed'
  },
})

const shouldAutoBuild = computed(
  () =>
    !!(
      dealDoc.value?.optin_submission &&
      !lifecycle.value?.quotation &&
      !quotes.value.length &&
      !buildAttempted.value
    ),
)

watch(
  shouldAutoBuild,
  (trigger) => {
    if (trigger) {
      buildAttempted.value = true
      buildQuoteResource.submit({ deal: props.dealId })
    }
  },
  { immediate: true },
)

// ── Inline editor selection (non-OIS) ──────────────────────────────────────────

const selectedQuote = ref(null)
const selectedQuoteData = computed(
  () =>
    quotes.value.find((quote) => quote.name === selectedQuote.value) ?? null,
)

function selectQuote(name) {
  selectedQuote.value = name
}

// Honor ?quote= deep-link (from the standalone Quotes list) and default to the
// most recent quote once the list resolves.
watch(
  [quotes, () => route.query.quote],
  ([list, deepLink]) => {
    if (isOis.value) return
    if (deepLink && list.some((q) => q.name === deepLink)) {
      selectedQuote.value = deepLink
    } else if (!selectedQuote.value && list.length) {
      selectedQuote.value = list[0].name
    }
  },
  { immediate: true },
)

// ── Create a new blank quote (non-OIS) ─────────────────────────────────────────

const creating = ref(false)
const createResource_ = createResource({ url: 'crm.api.quotes.create_quote' })

async function createQuote() {
  creating.value = true
  try {
    const res = await createResource_.submit({ deal: props.dealId })
    await quotesResource.reload()
    selectedQuote.value = res?.name ?? null
    toast.success(__('Draft quote created'))
  } catch (err) {
    toast.error(
      err?.messages?.[0] ?? err?.message ?? __('Failed to create quote'),
    )
  } finally {
    creating.value = false
  }
}

// ── Internal Opt-In summary ───────────────────────────────────────────────────

const showOptInSummaryDialog = ref(false)
const summaryNetwork = ref('')
const summaryError = ref('')
const submittingSummary = ref(false)
const networksResource = createResource({
  url: 'crm.api.optin_admin.list_networks',
  makeParams: () => ({ page: 0, page_size: 200 }),
  auto: true,
})
const networkOptions = computed(() =>
  (networksResource.data?.rows ?? [])
    .filter((network) => network.enabled)
    .map((network) => ({ label: network.display_name, value: network.slug })),
)
const linkedNetwork = computed(
  () =>
    (networksResource.data?.rows ?? []).find(
      (network) => network.slug === dealDoc.value?.optin_network,
    ) ?? null,
)
const linkedNetworkName = computed(
  () => linkedNetwork.value?.display_name || dealDoc.value?.optin_network || '',
)
const priceListsResource = createResource({
  url: 'crm.api.quotes.list_price_lists',
  auto: true,
})
const priceListOptions = computed(() => priceListsResource.data ?? [])
const submitSummaryResource = createResource({
  url: 'crm.api.optin.submit_deal_optin_summary',
})

function openSummaryDialog() {
  summaryNetwork.value = dealDoc.value?.optin_network || ''
  summaryError.value = ''
  showOptInSummaryDialog.value = true
}

async function submitOptInSummary() {
  if (!selectedQuote.value || !summaryNetwork.value) return
  submittingSummary.value = true
  summaryError.value = ''
  try {
    await submitSummaryResource.submit({
      deal: props.dealId,
      quote: selectedQuote.value,
      network_slug: summaryNetwork.value,
    })
    showOptInSummaryDialog.value = false
    toast.success(__('Opt-In summary submitted'))
    await dealDocResource.reload()
    await lifecycleResource.reload()
    await quotesResource.reload()
  } catch (error) {
    summaryError.value =
      error?.messages?.[0] ??
      error?.message ??
      __('Could not submit Opt-In summary')
  } finally {
    submittingSummary.value = false
  }
}

const showInvitationDialog = ref(false)
const invitationPriceList = ref('')
const invitationError = ref('')
const sendingInvitation = ref(false)
const sendInvitationResource = createResource({
  url: 'crm.api.optin.send_deal_optin_invitation',
})

function openInvitationDialog() {
  invitationPriceList.value = linkedNetwork.value?.price_list_override || ''
  invitationError.value = ''
  showInvitationDialog.value = true
}

async function sendInvitation() {
  sendingInvitation.value = true
  invitationError.value = ''
  try {
    const result = await sendInvitationResource.submit({
      deal: props.dealId,
      price_list: invitationPriceList.value,
    })
    showInvitationDialog.value = false
    toast.success(__('Opt-In invitation sent to {0}', [result.sent_to]))
    emit('email-dispatched')
  } catch (error) {
    invitationError.value =
      error?.messages?.[0] ??
      error?.message ??
      __('Could not send Opt-In invitation')
  } finally {
    sendingInvitation.value = false
  }
}

// ── Quote actions ─────────────────────────────────────────────────────────────

const sendingName = ref(null)
const actionName = ref(null)

const sendResource = createResource({ url: 'crm.api.quotes.send_quote' })
const acceptResource = createResource({ url: 'crm.api.quotes.accept_quote' })
const rejectResource = createResource({ url: 'crm.api.quotes.reject_quote' })

async function sendQuote(name) {
  sendingName.value = name
  try {
    await sendResource.submit({ quote_name: name })
    quotesResource.reload()
    emit('email-dispatched')
  } finally {
    sendingName.value = null
  }
}

async function acceptQuote(name) {
  actionName.value = name
  try {
    await acceptResource.submit({ quote_name: name })
    quotesResource.reload()
  } finally {
    actionName.value = null
  }
}

const showRejectDialog = ref(false)
const rejectTargetName = ref(null)

function confirmReject(name) {
  rejectTargetName.value = name
  showRejectDialog.value = true
}

async function doReject() {
  actionName.value = rejectTargetName.value
  try {
    await rejectResource.submit({ quote_name: rejectTargetName.value })
    quotesResource.reload()
    showRejectDialog.value = false
  } finally {
    actionName.value = null
    rejectTargetName.value = null
  }
}

function downloadPdf(name) {
  window.open(
    `/api/method/frappe.utils.print_format.download_pdf?doctype=Quotation&name=${encodeURIComponent(name)}&format=Careverse+Quote+Standard`,
    '_blank',
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

function fmtKes(v) {
  if (!v && v !== 0) return '—'
  const n = parseFloat(v)
  if (n >= 1_000_000) return 'KES ' + (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return 'KES ' + (n / 1_000).toFixed(1) + 'K'
  return 'KES ' + n.toLocaleString()
}

function isExpired(q) {
  if (!q.valid_until || q.status === 'Accepted' || q.status === 'Rejected')
    return false
  return new Date(q.valid_until) < new Date()
}

function pillClass(q) {
  const base = 'rounded-full px-2 py-0.5 text-xs font-medium'
  if (isExpired(q))
    return `${base} bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400`
  const map = {
    Draft: `${base} bg-surface-gray-2 text-ink-gray-6 dark:bg-surface-gray-4 dark:text-ink-gray-4`,
    Sent: `${base} bg-surface-gray-3 text-ink-gray-8 dark:bg-surface-gray-5 dark:text-ink-gray-3`,
    Accepted: `${base} bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400`,
    Rejected: `${base} bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400`,
  }
  return map[q.status] ?? map.Draft
}

function timeAgo(dateStr) {
  if (!dateStr) return ''
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (diff < 60) return __('just now')
  if (diff < 3600) return Math.floor(diff / 60) + ' ' + __('min ago')
  if (diff < 86400) return Math.floor(diff / 3600) + ' ' + __('hr ago')
  if (diff < 86400 * 7) return Math.floor(diff / 86400) + ' ' + __('d ago')
  return formatDate(dateStr)
}
</script>
