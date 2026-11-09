<template>
  <div class="flex flex-col gap-6 px-4 py-5 sm:px-8">
    <!-- KPI row -->
    <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <div class="flex flex-col gap-1 rounded-lg border border-outline-gray-2 bg-surface-white p-4">
        <span class="text-xs font-medium text-ink-gray-5">{{
          __('Package Paid')
        }}</span>
        <div class="flex items-center gap-2">
          <span class="text-2xl font-semibold tabular-nums text-ink-gray-9">{{
            paid.label
          }}</span>
          <Badge :label="paid.label" :theme="paid.theme" size="sm" variant="subtle" />
        </div>
        <span class="text-xs text-ink-gray-4">
          {{ money(summary.paid_amount) }}
          {{ __('paid so far') }}
        </span>
      </div>

      <div class="flex flex-col gap-1 rounded-lg border border-outline-gray-2 bg-surface-white p-4">
        <span class="text-xs font-medium text-ink-gray-5">{{
          __('Pending Orders')
        }}</span>
        <div class="flex items-center gap-2">
          <span class="text-2xl font-semibold tabular-nums text-ink-gray-9">{{
            summary.open_orders
          }}</span>
          <Badge
            v-if="summary.open_orders > 0"
            :label="__('Open')"
            size="sm"
            theme="amber"
            variant="subtle"
          />
          <Badge
            v-else
            :label="__('None')"
            size="sm"
            theme="green"
            variant="subtle"
          />
        </div>
        <span class="text-xs text-ink-gray-4">
          {{ money(summary.open_amount) }} {{ __('open value') }}
        </span>
      </div>

      <div class="flex flex-col gap-1 rounded-lg border border-outline-gray-2 bg-surface-white p-4">
        <span class="text-xs font-medium text-ink-gray-5">{{
          __('Site Provisioning')
        }}</span>
        <div class="flex items-center gap-2">
          <span class="text-2xl font-semibold text-ink-gray-9">
            {{ provisioning }}
          </span>
        </div>
        <span class="text-xs text-ink-gray-4">
          {{ summary.sites_live }} / {{ summary.sites_total }}
          {{ __('facilities live') }}
        </span>
      </div>

      <div class="flex flex-col gap-1 rounded-lg border border-outline-gray-2 bg-surface-white p-4">
        <span class="text-xs font-medium text-ink-gray-5">{{
          __('Outstanding Balance')
        }}</span>
        <div class="flex items-center gap-2">
          <span class="text-2xl font-semibold tabular-nums text-ink-gray-9">
            {{ money(summary.outstanding) }}
          </span>
          <Badge
            v-if="summary.outstanding > 0"
            :label="__('Due')"
            size="sm"
            theme="red"
            variant="subtle"
          />
          <Badge
            v-else
            :label="__('Clear')"
            size="sm"
            theme="green"
            variant="subtle"
          />
        </div>
        <span class="text-xs text-ink-gray-4">
          {{ summary.invoices }} {{ __('invoice(s) on file') }}
        </span>
      </div>
    </div>

    <!-- Partner -->
    <section v-if="data.partners?.length" class="rounded-lg border border-outline-gray-2 bg-surface-white">
      <h2 class="border-b border-outline-gray-2 px-4 py-3 text-sm font-semibold text-ink-gray-9">
        {{ __('Partner Details') }}
      </h2>
      <div class="divide-y divide-outline-gray-2">
        <div
          v-for="partner in data.partners"
          :key="partner.kind + '-' + partner.ref"
          class="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
        >
          <div class="flex items-center gap-3">
            <Badge
              :label="partnerKindLabel(partner.kind)"
              size="sm"
              theme="violet"
              variant="subtle"
            />
            <div>
              <p class="font-medium text-ink-gray-9">{{ partner.name }}</p>
              <p v-if="partner.contact_email" class="text-xs text-ink-gray-5">
                {{ partner.contact_email }}
              </p>
            </div>
          </div>
          <div class="flex items-center gap-2 text-xs text-ink-gray-5">
            <span v-if="partner.partner_id" class="rounded bg-surface-gray-2 px-2 py-0.5 tabular-nums">
              {{ partner.partner_id }}
            </span>
            <span v-if="partner.partner_type">{{ partner.partner_type }}</span>
            <span v-if="partner.partner_rm">{{ partner.partner_rm }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Customer & Deal -->
    <section class="rounded-lg border border-outline-gray-2 bg-surface-white">
      <h2 class="border-b border-outline-gray-2 px-4 py-3 text-sm font-semibold text-ink-gray-9">
        {{ __('Customer') }}
      </h2>
      <div class="px-4 py-3">
        <template v-if="data.organization">
          <div class="flex flex-wrap items-center gap-2">
            <p class="text-lg font-semibold text-ink-gray-9">
              {{ data.organization.organization_name }}
            </p>
            <Badge
              v-if="data.organization.industry"
              :label="data.organization.industry"
              size="sm"
              theme="blue"
              variant="subtle"
            />
            <Badge
              v-if="data.organization.territory"
              :label="data.organization.territory"
              size="sm"
              theme="gray"
              variant="subtle"
            />
          </div>
          <dl class="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
            <div>
              <dt class="text-xs text-ink-gray-4">{{ __('Website') }}</dt>
              <dd class="text-ink-gray-9">
                <a
                  v-if="data.organization.website"
                  :href="data.organization.website"
                  target="_blank"
                  rel="noopener"
                  class="text-ink-blue-6 hover:underline"
                  >{{ data.organization.website }}</a
                >
                <span v-else>—</span>
              </dd>
            </div>
            <div>
              <dt class="text-xs text-ink-gray-4">{{ __('Employees') }}</dt>
              <dd class="text-ink-gray-9">
                {{ data.organization.no_of_employees || '—' }}
              </dd>
            </div>
            <div>
              <dt class="text-xs text-ink-gray-4">{{ __('Annual Revenue') }}</dt>
              <dd class="tabular-nums text-ink-gray-9">
                {{ money(data.organization.annual_revenue, data.organization.currency) }}
              </dd>
            </div>
            <div>
              <dt class="text-xs text-ink-gray-4">{{ __('Deals') }}</dt>
              <dd class="text-ink-gray-9">{{ data.deals?.length || 0 }}</dd>
            </div>
          </dl>
        </template>
        <div v-else class="px-4 py-6 text-sm text-ink-gray-5">
          {{ __('No customer record found for this deal.') }}
        </div>

        <div
          v-if="data.deal"
          class="mt-3 flex flex-wrap items-center gap-2 border-t border-outline-gray-2 pt-3 text-sm"
        >
          <span class="font-medium text-ink-gray-9">{{ data.deal.name }}</span>
          <Badge
            v-if="data.deal.status"
            :label="data.deal.status"
            size="sm"
            :theme="dealStatusTheme(data.deal.status)"
            variant="subtle"
          />
          <span class="text-ink-gray-5">{{ money(data.deal.deal_value, data.deal.currency) }}</span>
          <span v-if="data.deal.email" class="text-ink-gray-5">{{ data.deal.email }}</span>
          <span v-if="data.deal.phone" class="text-ink-gray-5">{{ data.deal.phone }}</span>
          <span v-if="data.deal.mobile_no" class="text-ink-gray-5">{{ data.deal.mobile_no }}</span>
        </div>
      </div>
    </section>

    <!-- Orders -->
    <section
      class="rounded-lg border border-outline-gray-2 bg-surface-white"
      data-testid="c360-orders"
    >
      <h2 class="border-b border-outline-gray-2 px-4 py-3 text-sm font-semibold text-ink-gray-9">
        {{ __('Orders') }}
      </h2>
      <div v-if="data.orders?.length" class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left text-xs text-ink-gray-5">
              <th class="px-4 py-2 font-medium">{{ __('Order') }}</th>
              <th v-if="showFacilityColumn" class="px-4 py-2 font-medium">
                {{ __('Facility') }}
              </th>
              <th class="px-4 py-2 font-medium">{{ __('Date') }}</th>
              <th class="px-4 py-2 font-medium">{{ __('Amount') }}</th>
              <th class="px-4 py-2 font-medium">{{ __('Status') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-outline-gray-2">
              <tr
                v-for="order in data.orders"
                :key="order.name"
                data-testid="c360-order-row"
              >
                <td class="px-4 py-2">
                  <a
                    v-if="recordLink('Sales Order', order.name)"
                    :href="recordLink('Sales Order', order.name)"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="text-ink-blue-6 hover:underline"
                    >{{ order.name }}</a
                  >
                  <span v-else class="text-ink-gray-9">{{ order.name }}</span>
                </td>
              <td v-if="showFacilityColumn" class="px-4 py-2 text-ink-gray-5">
                {{ facilityLabel(order) }}
              </td>
              <td class="px-4 py-2 text-ink-gray-5">{{ formatDate(order.transaction_date) }}</td>
              <td class="px-4 py-2 tabular-nums text-ink-gray-9">
                {{ money(order.grand_total, order.currency) }}
              </td>
              <td class="px-4 py-2">
                <Badge
                  v-if="order.open"
                  :label="__('Open')"
                  size="sm"
                  theme="amber"
                  variant="subtle"
                />
                <Badge
                  v-else
                  :label="__('Billed')"
                  size="sm"
                  theme="green"
                  variant="subtle"
                />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="flex flex-col items-center gap-1 px-4 py-6">
        <p class="text-sm font-medium text-ink-gray-7">{{ __('No orders yet') }}</p>
        <p class="text-xs text-ink-gray-4">
          {{
            facilityMode
              ? __('Sales orders will appear here once created for this facility.')
              : __('Sales orders will appear here once created for this customer.')
          }}
        </p>
      </div>
    </section>

    <!-- Quotes -->
    <section
      class="rounded-lg border border-outline-gray-2 bg-surface-white"
      data-testid="c360-quotes"
    >
      <h2 class="border-b border-outline-gray-2 px-4 py-3 text-sm font-semibold text-ink-gray-9">
        {{ __('Quotes') }}
      </h2>
      <div v-if="data.quotes?.length" class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left text-xs text-ink-gray-5">
              <th class="px-4 py-2 font-medium">{{ __('Quote') }}</th>
              <th v-if="showFacilityColumn" class="px-4 py-2 font-medium">
                {{ __('Facility') }}
              </th>
              <th class="px-4 py-2 font-medium">{{ __('Date') }}</th>
              <th class="px-4 py-2 font-medium">{{ __('Amount') }}</th>
              <th class="px-4 py-2 font-medium">{{ __('Valid till') }}</th>
              <th class="px-4 py-2 font-medium">{{ __('Status') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-outline-gray-2">
            <tr v-for="quote in data.quotes" :key="quote.name" data-testid="c360-quote-row">
              <td class="px-4 py-2">
                <a
                  v-if="recordLink('Quotation', quote.name)"
                  :href="recordLink('Quotation', quote.name)"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="text-ink-blue-6 hover:underline"
                  >{{ quote.name }}</a
                >
                <span v-else class="text-ink-gray-9">{{ quote.name }}</span>
              </td>
              <td v-if="showFacilityColumn" class="px-4 py-2 text-ink-gray-5">
                {{ facilityLabel(quote) }}
              </td>
              <td class="px-4 py-2 text-ink-gray-5">{{ formatDate(quote.transaction_date) }}</td>
              <td class="px-4 py-2 tabular-nums text-ink-gray-9">
                {{ money(quote.grand_total, quote.currency) }}
              </td>
              <td class="px-4 py-2 text-ink-gray-5">
                {{ quote.valid_till ? formatDate(quote.valid_till) : '—' }}
              </td>
              <td class="px-4 py-2">
                <Badge
                  :label="quoteState(quote).label"
                  size="sm"
                  :theme="quoteState(quote).theme"
                  variant="subtle"
                />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="flex flex-col items-center gap-1 px-4 py-6">
        <p class="text-sm font-medium text-ink-gray-7">{{ __('No quotes yet') }}</p>
        <p class="text-xs text-ink-gray-4">
          {{
            facilityMode
              ? __('Quotations will appear here once raised for this facility.')
              : __('Quotations will appear here once raised for this customer.')
          }}
        </p>
      </div>
    </section>

    <!-- Billing -->
    <section
      class="rounded-lg border border-outline-gray-2 bg-surface-white"
      data-testid="c360-billing"
    >
      <h2 class="border-b border-outline-gray-2 px-4 py-3 text-sm font-semibold text-ink-gray-9">
        {{ __('Billing') }}
      </h2>
      <div class="flex flex-col gap-4 px-4 py-3">
        <div class="overflow-x-auto">
          <table v-if="data.invoices?.length" class="w-full text-sm">
            <thead>
              <tr class="text-left text-xs text-ink-gray-5">
                <th class="px-2 py-2 font-medium">{{ __('Invoice') }}</th>
                <th v-if="showFacilityColumn" class="px-2 py-2 font-medium">
                  {{ __('Facility') }}
                </th>
                <th class="px-2 py-2 font-medium">{{ __('Date') }}</th>
                <th class="px-2 py-2 font-medium">{{ __('Total') }}</th>
                <th class="px-2 py-2 font-medium">{{ __('Outstanding') }}</th>
                <th class="px-2 py-2 font-medium">{{ __('Due') }}</th>
                <th class="px-2 py-2 font-medium">{{ __('Status') }}</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-outline-gray-2">
              <tr
                v-for="invoice in data.invoices"
                :key="invoice.name"
                data-testid="c360-invoice-row"
              >
                <td class="px-2 py-2">
                  <a
                    v-if="recordLink('Sales Invoice', invoice.name)"
                    :href="recordLink('Sales Invoice', invoice.name)"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="text-ink-blue-6 hover:underline"
                    >{{ invoice.name }}</a
                  >
                  <span v-else class="text-ink-gray-9">{{ invoice.name }}</span>
                </td>
                <td v-if="showFacilityColumn" class="px-2 py-2 text-ink-gray-5">
                  {{ facilityLabel(invoice) }}
                </td>
                <td class="px-2 py-2 text-ink-gray-5">{{ formatDate(invoice.creation) }}</td>
                <td class="px-2 py-2 tabular-nums text-ink-gray-9">
                  {{ money(invoice.grand_total, invoice.currency) }}
                </td>
                <td class="px-2 py-2 tabular-nums text-ink-gray-9">
                  {{ money(invoice.outstanding, invoice.currency) }}
                </td>
                <td class="px-2 py-2 text-ink-gray-5">{{ formatDate(invoice.due_date) }}</td>
                <td class="px-2 py-2">
                  <Badge
                    :label="invoiceState(invoice).label"
                    size="sm"
                    :theme="invoiceState(invoice).theme"
                    variant="subtle"
                  />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div
          v-if="!data.invoices?.length"
          class="flex flex-col items-center gap-1 px-4 py-6"
        >
          <p class="text-sm font-medium text-ink-gray-7">{{ __('No invoices yet') }}</p>
          <p class="text-xs text-ink-gray-4">
            {{ __('Invoices will appear here once billing starts.') }}
          </p>
        </div>
        <div v-if="data.payments?.length">
          <h3 class="mb-2 text-xs font-medium text-ink-gray-5">{{
            __('Payments Received')
          }}</h3>
          <ul class="flex flex-col gap-1 text-sm">
              <li
                v-for="payment in data.payments"
                :key="payment.name"
                class="flex items-center justify-between"
                data-testid="c360-payment-row"
              >
                <span class="flex items-center gap-1 text-ink-gray-5">
                  <a
                    v-if="recordLink('Payment Entry', payment.name)"
                    :href="recordLink('Payment Entry', payment.name)"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="text-ink-blue-6 hover:underline"
                    >{{ payment.name }}</a
                  >
                  <span v-else>{{ payment.name }}</span>
                  {{ formatDate(payment.posting_date) }}
                  <template v-if="payment.party"> · {{ payment.party }}</template>
                </span>
                <span class="tabular-nums text-ink-gray-9">
                  {{ money(payment.paid_amount) }}
                </span>
              </li>
          </ul>
        </div>
      </div>
    </section>

    <!-- Facilities & provisioning -->
    <section
      class="rounded-lg border border-outline-gray-2 bg-surface-white"
      data-testid="c360-facilities"
    >
      <h2 class="border-b border-outline-gray-2 px-4 py-3 text-sm font-semibold text-ink-gray-9">
        {{ __('Facilities & Provisioning') }}
      </h2>
      <div class="px-4 py-3">
        <template v-if="data.facilities?.length">
          <div
            v-for="facility in data.facilities"
            :key="facility.name"
            class="border-b border-outline-gray-2 py-3 last:border-0"
            data-testid="c360-facility-row"
          >
            <div class="flex flex-wrap items-center gap-2">
              <a
                v-if="recordLink('CRM Pre-Qualified Facility', facility.name)"
                :href="recordLink('CRM Pre-Qualified Facility', facility.name)"
                target="_blank"
                rel="noopener noreferrer"
                class="font-medium text-ink-blue-6 hover:underline"
                >{{ facility.facility_name }}</a
              >
              <span v-else class="font-medium text-ink-gray-9">
                {{ facility.facility_name }}
              </span>
              <span class="rounded bg-surface-gray-2 px-2 py-0.5 text-xs text-ink-gray-5">
                {{ __('Facility ID') }}:
                <span class="tabular-nums">{{ facilityId(facility) || __('Not linked yet') }}</span>
              </span>
              <span class="rounded bg-surface-gray-2 px-2 py-0.5 text-xs text-ink-gray-5">
                {{ __('MFL') }}: <span class="tabular-nums">{{ facility.mfl_code }}</span>
              </span>
              <Badge
                v-if="facility.keph_level"
                :label="facility.keph_level"
                size="sm"
                theme="gray"
                variant="subtle"
              />
              <Badge
                v-if="facility.is_self_onboarded"
                :label="__('Self-Onboarded')"
                size="sm"
                theme="violet"
                variant="subtle"
              />
            </div>
            <div v-if="facility.memberships?.length" class="mt-2 flex flex-col gap-1">
              <div
                v-for="(membership, index) in facility.memberships"
                :key="index"
                class="flex flex-wrap items-center gap-2 text-sm"
              >
                <span class="text-ink-gray-9">
                  {{ membership.display_name || membership.network || __('Network') }}
                </span>
                <Badge
                  :label="siteState(membership).label"
                  size="sm"
                  :theme="siteState(membership).theme"
                  variant="subtle"
                />
                <Badge
                  v-if="membership.self_onboarding"
                  :label="__('Value Express')"
                  size="sm"
                  theme="blue"
                  variant="subtle"
                />
                <span class="text-xs text-ink-gray-5">
                  <template v-if="membership.contact_name">
                    {{ membership.contact_name }}
                    <template v-if="membership.contact_phone"> · </template>
                  </template>
                  {{ membership.contact_phone }}
                </span>
              </div>
            </div>
            <p v-else class="mt-1 text-xs text-ink-gray-4">{{
              __('No network memberships recorded')
            }}</p>
          </div>
        </template>
        <div
          v-else
          class="flex flex-col items-center gap-1 px-4 py-6"
        >
          <p class="text-sm font-medium text-ink-gray-7">{{
            __('No facilities on file')
          }}</p>
          <p class="text-xs text-ink-gray-4">
            {{ __('Facilities linked to this customer will appear here.') }}
          </p>
        </div>

        <div v-if="data.onboarding?.length" class="mt-3 border-t border-outline-gray-2 pt-3">
          <h3 class="mb-2 text-xs font-medium text-ink-gray-5">{{
            __('Onboarding Requests')
          }}</h3>
          <div class="flex flex-col gap-2">
            <div
              v-for="request in data.onboarding"
              :key="request.name"
              class="flex flex-wrap items-center gap-2 text-sm"
            >
              <span class="text-ink-gray-9">{{ request.name }}</span>
              <Badge
                :label="onboardingState(request).label"
                size="sm"
                :theme="onboardingState(request).theme"
                variant="subtle"
              />
              <span v-if="request.approval_status" class="text-xs text-ink-gray-5">
                {{ __('Approval') }}: {{ request.approval_status }}
              </span>
              <span
                v-if="request.careverse_provisioned_date"
                class="text-xs text-ink-gray-5"
              >
                {{ __('Provisioned') }} {{ formatDate(request.careverse_provisioned_date) }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Deals -->
    <section class="rounded-lg border border-outline-gray-2 bg-surface-white">
      <h2 class="border-b border-outline-gray-2 px-4 py-3 text-sm font-semibold text-ink-gray-9">
        {{ __('Deals') }}
      </h2>
      <div class="overflow-x-auto">
        <table v-if="data.deals?.length" class="w-full text-sm">
          <thead>
            <tr class="text-left text-xs text-ink-gray-5">
              <th class="px-4 py-2 font-medium">{{ __('Deal') }}</th>
              <th class="px-4 py-2 font-medium">{{ __('Status') }}</th>
              <th class="px-4 py-2 font-medium">{{ __('Value') }}</th>
              <th class="px-4 py-2 font-medium">{{ __('Partner') }}</th>
              <th class="px-4 py-2 font-medium">{{ __('Owner') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-outline-gray-2">
            <tr v-for="item in data.deals" :key="item.name">
              <td class="px-4 py-2">
                <router-link
                  :to="{ name: 'Deal', params: { dealId: item.name } }"
                  class="text-ink-blue-6 hover:underline"
                >
                  {{ item.name }}
                </router-link>
              </td>
              <td class="px-4 py-2">
                <Badge
                  v-if="item.status"
                  :label="item.status"
                  size="sm"
                  :theme="dealStatusTheme(item.status)"
                  variant="subtle"
                />
              </td>
              <td class="px-4 py-2 tabular-nums text-ink-gray-9">
                {{ money(item.deal_value, item.currency) }}
              </td>
              <td class="px-4 py-2 text-ink-gray-5">
                {{ item.partner || '—' }}
              </td>
              <td class="px-4 py-2 text-ink-gray-5">
                {{ item.deal_owner || '—' }}
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="px-4 py-4 text-sm text-ink-gray-5">
          {{ __('No deals for this customer') }}
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Badge } from 'frappe-ui'
import { formatDate } from '@/utils/index.js'
import { formatCurrency } from '@/utils/numberFormat.js'
import { cockpitRecordHref } from '@/pages/FinanceCockpit/composables/useFinanceNavigation.js'
import { facilityId } from '@/utils/facilityId.js'
import {
	facilityLabelFor,
	invoiceState,
	onboardingState,
	paidState,
	partnerKindLabel,
	provisioningHeadline,
	quoteState,
	siteState,
} from '@/utils/customer360.js'

const props = defineProps({
	data: { type: Object, default: null },
})

const summary = computed(() => props.data?.summary || {})
const paid = computed(() => paidState(summary.value))
const provisioning = computed(() => provisioningHeadline(summary.value))
const facilityMode = computed(() => props.data?.scope?.mode === 'facility')
// The organization view names each record's facility once there is more than one.
const showFacilityColumn = computed(
	() => !facilityMode.value && (props.data?.facilities?.length || 0) > 1,
)

function facilityLabel(row) {
	return facilityLabelFor(row?.facility_mfls, props.data?.facilities)
}

function money(value, currency) {
	if (value === null || value === undefined || value === '') return '0'
	return formatCurrency(value, '', currency || 'USD')
}

function dealStatusTheme(status) {
	const themes = {
		Won: 'green',
		Lost: 'red',
		Qualification: 'amber',
		Negotiation: 'blue',
	}
	return themes[status] || 'gray'
}

// Detail rows deep-link into the Finance Cockpit record view (the canonical
// href builder, same URLs the cockpit sidebar generates).
function recordLink(doctype, name) {
	return cockpitRecordHref(doctype, name, { absolute: true })
}
</script>
